"""Fetch and normalize Evergreen waterfall history for standalone triage."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Sequence, Tuple

from .models import (
    CANONICAL_TASK_STATUS_UNIVERSE,
    TaskOccurrence,
    VariantHistory,
    WaterfallVersion,
)

WATERFALL_HISTORY_QUERY = """
query WaterfallHistory($options: WaterfallOptions!, $tasksOptions: TaskFilterOptions!) {
  waterfall(options: $options) {
    flattenedVersions {
      id
      branch
      startTime
      revision
      finishTime
      tasks(options: $tasksOptions) {
        count
        data {
          id
          displayName
          execution
          buildVariant
          status
        }
      }
    }
  }
}
"""

QueryExecutor = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


def _get_query_executor(client: Any) -> QueryExecutor:
    execute_query = getattr(client, "_execute_query", None) or getattr(
        client, "execute_query", None
    )
    if execute_query is None:
        execute_query = getattr(client, "execute", None)
    if execute_query is None:
        raise TypeError(
            "Client must expose an async execute, execute_query, or _execute_query"
        )
    return execute_query


def _normalize_task_name(raw_task: dict[str, Any]) -> str:
    return raw_task.get("displayName") or raw_task.get("id") or "unknown-task"


def _normalize_version(
    project_identifier: str,
    variant: str,
    raw_version: dict[str, Any],
) -> WaterfallVersion:
    raw_tasks = ((raw_version.get("tasks") or {}).get("data")) or []
    tasks = tuple(
        TaskOccurrence(
            variant=variant,
            task_name=_normalize_task_name(raw_task),
            task_id=raw_task.get("id") or "unknown-task-id",
            status=raw_task.get("status") or "unknown",
            version_id=raw_version.get("id") or "unknown-version-id",
            revision=raw_version.get("revision"),
            branch=raw_version.get("branch"),
            start_time=raw_version["startTime"],
            finish_time=raw_version["finishTime"],
            execution=raw_task.get("execution"),
        )
        for raw_task in raw_tasks
    )
    return WaterfallVersion(
        project_identifier=project_identifier,
        variant=variant,
        version_id=raw_version.get("id") or "unknown-version-id",
        revision=raw_version.get("revision"),
        branch=raw_version.get("branch"),
        start_time=raw_version["startTime"],
        finish_time=raw_version["finishTime"],
        tasks=tasks,
    )


def normalize_variant_history(
    project_identifier: str,
    variant: str,
    waterfall_limit: int,
    raw_result: dict[str, Any],
    queried_statuses: Sequence[str] = CANONICAL_TASK_STATUS_UNIVERSE,
) -> VariantHistory:
    raw_versions = ((raw_result.get("waterfall") or {}).get("flattenedVersions")) or []
    normalized_versions: list[WaterfallVersion] = []
    skipped_missing_start_time = 0
    skipped_missing_finish_time = 0
    skipped_empty_tasks = 0

    for raw_version in raw_versions:
        if not raw_version.get("startTime"):
            skipped_missing_start_time += 1
            continue
        if not raw_version.get("finishTime"):
            skipped_missing_finish_time += 1
            continue

        tasks_obj = raw_version.get("tasks") or {}
        raw_tasks = (tasks_obj.get("data")) or []
        reported_task_count = tasks_obj.get("count")
        if (
            isinstance(reported_task_count, int)
            and reported_task_count > len(raw_tasks)
        ):
            version_id = raw_version.get("id") or "unknown-version-id"
            raise ValueError(
                "Waterfall task list was truncated by GraphQL limit for "
                f"variant={variant} version={version_id}: "
                f"received {len(raw_tasks)} of {reported_task_count} tasks"
            )
        if not raw_tasks:
            skipped_empty_tasks += 1
            continue

        normalized_versions.append(
            _normalize_version(project_identifier, variant, raw_version)
        )

    normalized_versions.sort(
        key=lambda version: (version.start_time, version.version_id),
        reverse=True,
    )

    return VariantHistory(
        project_identifier=project_identifier,
        variant=variant,
        waterfall_limit=waterfall_limit,
        queried_statuses=tuple(queried_statuses),
        fetched_version_count=len(raw_versions),
        skipped_missing_start_time=skipped_missing_start_time,
        skipped_missing_finish_time=skipped_missing_finish_time,
        skipped_empty_tasks=skipped_empty_tasks,
        versions=tuple(normalized_versions),
    )


async def fetch_variant_history(
    query_executor: QueryExecutor,
    project_identifier: str,
    variant: str,
    waterfall_limit: int = 200,
    queried_statuses: Sequence[str] = CANONICAL_TASK_STATUS_UNIVERSE,
) -> VariantHistory:
    result = await query_executor(
        WATERFALL_HISTORY_QUERY,
        {
            "options": {
                "projectIdentifier": project_identifier,
                "limit": waterfall_limit,
            },
            "tasksOptions": {
                "variant": variant,
                "statuses": list(queried_statuses),
                "limit": 1000,
            },
        },
    )
    return normalize_variant_history(
        project_identifier=project_identifier,
        variant=variant,
        waterfall_limit=waterfall_limit,
        raw_result=result,
        queried_statuses=queried_statuses,
    )


async def fetch_waterfall_history(
    query_executor: QueryExecutor,
    project_identifier: str,
    variants: Sequence[str],
    waterfall_limit: int = 200,
    queried_statuses: Sequence[str] = CANONICAL_TASK_STATUS_UNIVERSE,
) -> Tuple[VariantHistory, ...]:
    if not variants:
        raise ValueError("At least one variant must be provided")

    histories = await asyncio.gather(
        *[
            fetch_variant_history(
                query_executor=query_executor,
                project_identifier=project_identifier,
                variant=variant,
                waterfall_limit=waterfall_limit,
                queried_statuses=queried_statuses,
            )
            for variant in variants
        ]
    )
    return tuple(histories)


async def fetch_waterfall_history_from_client(
    client: Any,
    project_identifier: str,
    variants: Sequence[str],
    waterfall_limit: int = 200,
    queried_statuses: Sequence[str] = CANONICAL_TASK_STATUS_UNIVERSE,
) -> Tuple[VariantHistory, ...]:
    return await fetch_waterfall_history(
        query_executor=_get_query_executor(client),
        project_identifier=project_identifier,
        variants=variants,
        waterfall_limit=waterfall_limit,
        queried_statuses=queried_statuses,
    )
