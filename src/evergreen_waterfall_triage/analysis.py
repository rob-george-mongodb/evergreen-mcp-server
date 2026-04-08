"""Current/open streak analysis for Evergreen waterfall history."""

from __future__ import annotations

from collections import defaultdict
from typing import Optional, Sequence

from .fetch import fetch_waterfall_history_from_client
from .models import (
    CANONICAL_TASK_STATUS_UNIVERSE,
    FAILURE_COUNTING_STATUS,
    NEUTRAL_STATUSES,
    RESET_STATUS,
    TaskOccurrence,
    TaskStreak,
    TaskUrlBuilder,
    TriageReport,
    VariantHistory,
)
from .urls import get_task_url_template


def _build_streak(
    project_identifier: str,
    variant: str,
    task_name: str,
    occurrences: Sequence[TaskOccurrence],
    eligible_version_count: int,
) -> Optional[TaskStreak]:
    streak_occurrences: list[TaskOccurrence] = []
    pending_leading_neutral_occurrences: list[TaskOccurrence] = []
    failure_occurrences: list[TaskOccurrence] = []
    reset_occurrence: Optional[TaskOccurrence] = None

    for occurrence in occurrences:
        if occurrence.status == RESET_STATUS:
            if failure_occurrences:
                reset_occurrence = occurrence
            break

        if occurrence.status == FAILURE_COUNTING_STATUS:
            if pending_leading_neutral_occurrences:
                streak_occurrences.extend(pending_leading_neutral_occurrences)
                pending_leading_neutral_occurrences = []
            failure_occurrences.append(occurrence)
            streak_occurrences.append(occurrence)
            continue

        if failure_occurrences:
            streak_occurrences.append(occurrence)
        else:
            pending_leading_neutral_occurrences.append(occurrence)

    if not failure_occurrences:
        return None

    return TaskStreak(
        project_identifier=project_identifier,
        variant=variant,
        task_name=task_name,
        failure_count=len(failure_occurrences),
        truncated=reset_occurrence is None,
        eligible_version_count=eligible_version_count,
        searched_occurrence_count=len(streak_occurrences) + (1 if reset_occurrence else 0),
        latest_occurrence=streak_occurrences[0],
        latest_failure=failure_occurrences[0],
        oldest_failure=failure_occurrences[-1],
        occurrences=tuple(streak_occurrences),
        failure_occurrences=tuple(failure_occurrences),
        reset_occurrence=reset_occurrence,
    )


def analyze_current_streaks(
    project_identifier: str,
    histories: Sequence[VariantHistory],
    min_num_consecutive_failures: int = 1,
) -> TriageReport:
    if min_num_consecutive_failures < 1:
        raise ValueError("min_num_consecutive_failures must be >= 1")

    streaks: list[TaskStreak] = []

    for history in histories:
        occurrences_by_task: dict[str, list[TaskOccurrence]] = defaultdict(list)
        for version in history.versions:
            for task in version.tasks:
                occurrences_by_task[task.task_name].append(task)

        for task_name, occurrences in occurrences_by_task.items():
            streak = _build_streak(
                project_identifier=project_identifier,
                variant=history.variant,
                task_name=task_name,
                occurrences=occurrences,
                eligible_version_count=history.eligible_version_count,
            )
            if streak is None:
                continue
            if streak.failure_count < min_num_consecutive_failures:
                continue
            streaks.append(streak)

    streaks.sort(
        key=lambda streak: (
            -streak.failure_count,
            streak.variant,
            streak.task_name,
            streak.latest_occurrence.start_time or "",
        )
    )

    return TriageReport(
        project_identifier=project_identifier,
        variants_queried=tuple(history.variant for history in histories),
        waterfall_limit=max((history.waterfall_limit for history in histories), default=0),
        min_num_consecutive_failures=min_num_consecutive_failures,
        queried_statuses=tuple(CANONICAL_TASK_STATUS_UNIVERSE),
        histories=tuple(histories),
        streaks=tuple(streaks),
    )


def build_triage_output(
    project_identifier: str,
    histories: Sequence[VariantHistory],
    min_num_consecutive_failures: int = 1,
    task_url_builder: Optional[TaskUrlBuilder] = None,
) -> dict[str, object]:
    report = analyze_current_streaks(
        project_identifier=project_identifier,
        histories=histories,
        min_num_consecutive_failures=min_num_consecutive_failures,
    )
    template = get_task_url_template()

    def resolved_task_url_builder(occurrence: TaskOccurrence) -> str | None:
        if task_url_builder is not None:
            return task_url_builder(occurrence)
        return template.build_task_url(occurrence.task_id)

    eligible_versions_examined_by_variant = {
        history.variant: history.eligible_version_count for history in histories
    }

    return {
        "query": {
            "project_identifier": project_identifier,
            "variants": [history.variant for history in histories],
            "waterfall_limit": report.waterfall_limit,
            "min_num_consecutive_failures": report.min_num_consecutive_failures,
        },
        "rules": {
            "failure_count_statuses": [FAILURE_COUNTING_STATUS],
            "reset_statuses": [RESET_STATUS],
            "neutral_statuses": list(NEUTRAL_STATUSES),
        },
        "links": {
            "ui_base_url": template.base_url,
            "task_url_template": template.template_url,
        },
        "summary": {
            "eligible_versions_examined_by_variant": eligible_versions_examined_by_variant,
            "open_task_streak_count": len(report.streaks),
            "truncated_streak_count": sum(
                1 for streak in report.streaks if streak.truncated
            ),
        },
        "streaks": [
            {
                "variant": streak.variant,
                "task_name": streak.task_name,
                "consecutive_failure_count": streak.failure_count,
                "is_truncated_by_waterfall_limit": streak.truncated,
                "latest_failure": streak.latest_failure.to_dict(
                    resolved_task_url_builder
                ),
                "oldest_failure_in_window": streak.oldest_failure.to_dict(
                    resolved_task_url_builder
                ),
                "boundary": {
                    "reset_found": streak.reset_occurrence is not None,
                    "reset_status": (
                        streak.reset_occurrence.status
                        if streak.reset_occurrence is not None
                        else None
                    ),
                    "reset_version_id": (
                        streak.reset_occurrence.version_id
                        if streak.reset_occurrence is not None
                        else None
                    ),
                },
                "failures": [
                    occurrence.to_dict(resolved_task_url_builder)
                    for occurrence in streak.failure_occurrences
                ],
            }
            for streak in report.streaks
        ],
    }


async def run_current_streak_triage(
    client: object,
    project_identifier: str,
    variants: Sequence[str],
    waterfall_limit: int = 200,
    min_num_consecutive_failures: int = 1,
    task_url_builder: Optional[TaskUrlBuilder] = None,
) -> dict[str, object]:
    histories = await fetch_waterfall_history_from_client(
        client=client,
        project_identifier=project_identifier,
        variants=variants,
        waterfall_limit=waterfall_limit,
        queried_statuses=CANONICAL_TASK_STATUS_UNIVERSE,
    )
    return build_triage_output(
        project_identifier=project_identifier,
        histories=histories,
        min_num_consecutive_failures=min_num_consecutive_failures,
        task_url_builder=task_url_builder,
    )
