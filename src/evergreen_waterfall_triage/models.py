"""Typed models for standalone Evergreen waterfall streak triage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Tuple

CANONICAL_TASK_STATUS_UNIVERSE: tuple[str, ...] = (
    "blocked",
    "failed",
    "undispatched",
    "will-run",
    "aborted",
    "dispatched",
    "known-issue",
    "task-timed-out",
    "test-timed-out",
    "setup-failed",
    "system-failed",
    "system-timed-out",
    "started",
    "system-unresponsive",
    "success",
)
FAILURE_COUNTING_STATUS = "failed"
RESET_STATUS = "success"
NEUTRAL_STATUSES: tuple[str, ...] = tuple(
    status
    for status in CANONICAL_TASK_STATUS_UNIVERSE
    if status not in {FAILURE_COUNTING_STATUS, RESET_STATUS}
)

TaskUrlBuilder = Callable[["TaskOccurrence"], Optional[str]]


@dataclass(frozen=True)
class TaskOccurrence:
    variant: str
    task_name: str
    task_id: str
    status: str
    version_id: str
    the_actual_variant_we_should_stop_using_the_incomprehensible_display_name_ones: Optional[str] = None
    revision: Optional[str] = None
    branch: Optional[str] = None
    start_time: Optional[str] = None
    finish_time: Optional[str] = None
    execution: Optional[int] = None

    @property
    def streak_key(self) -> Tuple[str, str]:
        return (self.variant, self.task_name)

    def to_dict(self, task_url_builder: Optional[TaskUrlBuilder] = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "variant": self.variant,
            "task_name": self.task_name,
            "task_id": self.task_id,
            "status": self.status,
            "version_id": self.version_id,
            "the_actual_variant_we_should_stop_using_the_incomprehensible_display_name_ones": self.the_actual_variant_we_should_stop_using_the_incomprehensible_display_name_ones,
            "revision": self.revision,
            "branch": self.branch,
            "start_time": self.start_time,
            "finish_time": self.finish_time,
            "execution": self.execution,
        }
        if task_url_builder is not None:
            task_url = task_url_builder(self)
            if task_url:
                payload["task_url"] = task_url
        return payload


@dataclass(frozen=True)
class WaterfallVersion:
    project_identifier: str
    variant: str
    version_id: str
    revision: Optional[str]
    branch: Optional[str]
    start_time: str
    finish_time: str
    tasks: Tuple[TaskOccurrence, ...]

    def to_dict(self, task_url_builder: Optional[TaskUrlBuilder] = None) -> dict[str, Any]:
        return {
            "project_identifier": self.project_identifier,
            "variant": self.variant,
            "version_id": self.version_id,
            "revision": self.revision,
            "branch": self.branch,
            "start_time": self.start_time,
            "finish_time": self.finish_time,
            "task_count": len(self.tasks),
            "tasks": [task.to_dict(task_url_builder) for task in self.tasks],
        }


@dataclass(frozen=True)
class VariantHistory:
    project_identifier: str
    variant: str
    waterfall_limit: int
    queried_statuses: Tuple[str, ...]
    fetched_version_count: int
    skipped_missing_start_time: int = 0
    skipped_missing_finish_time: int = 0
    skipped_empty_tasks: int = 0
    versions: Tuple[WaterfallVersion, ...] = field(default_factory=tuple)

    @property
    def eligible_version_count(self) -> int:
        return len(self.versions)

    @property
    def oldest_fetched_eligible_reached(self) -> bool:
        return self.eligible_version_count > 0

    def to_dict(self, task_url_builder: Optional[TaskUrlBuilder] = None) -> dict[str, Any]:
        return {
            "project_identifier": self.project_identifier,
            "variant": self.variant,
            "waterfall_limit": self.waterfall_limit,
            "queried_statuses": list(self.queried_statuses),
            "fetched_version_count": self.fetched_version_count,
            "eligible_version_count": self.eligible_version_count,
            "skipped_missing_start_time": self.skipped_missing_start_time,
            "skipped_missing_finish_time": self.skipped_missing_finish_time,
            "skipped_empty_tasks": self.skipped_empty_tasks,
            "versions": [
                version.to_dict(task_url_builder) for version in self.versions
            ],
        }


@dataclass(frozen=True)
class TaskStreak:
    project_identifier: str
    variant: str
    task_name: str
    failure_count: int
    truncated: bool
    eligible_version_count: int
    searched_occurrence_count: int
    latest_occurrence: TaskOccurrence
    latest_failure: TaskOccurrence
    oldest_failure: TaskOccurrence
    occurrences: Tuple[TaskOccurrence, ...]
    failure_occurrences: Tuple[TaskOccurrence, ...]
    reset_occurrence: Optional[TaskOccurrence] = None

    def to_dict(self, task_url_builder: Optional[TaskUrlBuilder] = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "project_identifier": self.project_identifier,
            "variant": self.variant,
            "task_name": self.task_name,
            "failure_count": self.failure_count,
            "truncated": self.truncated,
            "eligible_version_count": self.eligible_version_count,
            "searched_occurrence_count": self.searched_occurrence_count,
            "latest_status": self.latest_occurrence.status,
            "latest_version_id": self.latest_occurrence.version_id,
            "latest_revision": self.latest_occurrence.revision,
            "oldest_failure_version_id": self.oldest_failure.version_id,
            "oldest_failure_revision": self.oldest_failure.revision,
            "latest_occurrence": self.latest_occurrence.to_dict(task_url_builder),
            "latest_failure": self.latest_failure.to_dict(task_url_builder),
            "oldest_failure": self.oldest_failure.to_dict(task_url_builder),
            "reset_occurrence": None,
            "occurrences": [
                occurrence.to_dict(task_url_builder) for occurrence in self.occurrences
            ],
            "failure_occurrences": [
                occurrence.to_dict(task_url_builder)
                for occurrence in self.failure_occurrences
            ],
        }
        if self.reset_occurrence is not None:
            payload["reset_occurrence"] = self.reset_occurrence.to_dict(
                task_url_builder
            )
        return payload


@dataclass(frozen=True)
class TriageReport:
    project_identifier: str
    variants_queried: Tuple[str, ...]
    waterfall_limit: int
    min_num_consecutive_failures: int
    queried_statuses: Tuple[str, ...]
    histories: Tuple[VariantHistory, ...]
    streaks: Tuple[TaskStreak, ...]
