"""Waterfall failed tasks tools for Evergreen MCP server

Provides functionality to fetch and normalize recent failed tasks across
waterfall (flattened) versions for specified build variants.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

DEFAULT_FAILED_STATUSES = ["failed", "system-failed", "task-timed-out"]

async def fetch_waterfall_failed_tasks(
    client,
    arguments: Dict[str, Any],
) -> Dict[str, Any]:
    """Fetch and normalize failed tasks from the waterfall view.

    Args:
        client: EvergreenGraphQLClient instance
        arguments: Tool arguments containing project_identifier and variant(s)

    Returns:
        Normalized structure with versions and their failed tasks.
    """
    project_identifier = arguments.get("project_identifier")
    if not project_identifier:
        raise ValueError("project_identifier parameter is required")

    # Support single variant for convenience plus multi-variant list.
    variant = arguments.get("variant")
    variants = arguments.get("variants", []) or []
    if variant:
        variants.append(variant)

    # Deduplicate variants
    variants = sorted(list(set(filter(None, variants))))
    if not variants:
        raise ValueError("At least one variant must be provided via variant or variants")

    statuses = arguments.get("statuses") or DEFAULT_FAILED_STATUSES
    waterfall_limit = arguments.get("waterfall_limit", 1)

    logger.info(
        "Fetching waterfall failed tasks: project=%s variants=%s limit=%s statuses=%s",
        project_identifier,
        variants,
        waterfall_limit,
        statuses,
    )

    raw_versions = await client.get_waterfall_failed_tasks(
        project_identifier=project_identifier,
        variants=variants,
        statuses=statuses,
        waterfall_limit=waterfall_limit,
    )

    # Client now returns at most one most recent failing version or empty list
    if not raw_versions:
        return {
            "project_identifier": project_identifier,
            "variants_queried": variants,
            "statuses": statuses,
            "versions": [],
            "summary": {
                "total_versions_with_failures": 0,
                "total_failed_tasks": 0,
                "variants": variants,
                "suggested_next_steps": [
                    "Verify variant names and failure statuses",
                    "Try increasing waterfall_limit if failures are older",
                ],
                "note": "No failing version found",
            },
        }

    version = raw_versions[0]
    tasks = version.get("tasks", []) or []
    processed_tasks: List[Dict[str, Any]] = []
    for task in tasks:
        task_id = task.get("id")
        processed_tasks.append(
            {
                "task_id": task_id,
                "task_name": task.get("displayName"),
                "status": task.get("status"),
            }
        )

    response_version = {
        "version_id": version.get("id"),
        "revision": version.get("revision"),
        "branch": version.get("branch"),
        "start_time": version.get("startTime"),
        "finish_time": version.get("finishTime"),
        "failed_task_count": len(processed_tasks),
        "failed_tasks": processed_tasks,
        "variants_with_failures": version.get("variants", []),
    }

    response = {
        "project_identifier": project_identifier,
        "variants_queried": variants,
        "statuses": statuses,
        "versions": [response_version],
        "summary": {
            "total_versions_with_failures": 1,
            "total_failed_tasks": len(processed_tasks),
            "variants": variants,
            "suggested_next_steps": [
                "Invoke get_task_logs_evergreen on a task_id to inspect errors",
                "Invoke get_task_test_results_evergreen on tasks suspected of test failures",
            ],
        },
    }

    logger.info(
        "Waterfall failed tasks normalized: version=%s tasks=%s",
        response_version["version_id"],
        len(processed_tasks),
    )
    return response
