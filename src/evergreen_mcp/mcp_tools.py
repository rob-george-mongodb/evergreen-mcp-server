"""FastMCP tool definitions for Evergreen server

This module contains all MCP tool definitions using FastMCP decorators.
Tools are registered with the FastMCP server instance.
"""

import json
import logging
from typing import Annotated, Any, Dict, Sequence
from fastmcp import Context, FastMCP

import mcp.types as types

from .evergreen import download_task_artifacts
from .failed_jobs_tools import (
    fetch_patch_failed_jobs,
    fetch_task_logs,
    fetch_task_test_results,
    fetch_user_recent_patches,
)
from .waterfall_tools import fetch_waterfall_failed_tasks

logger = logging.getLogger(__name__)


def register_tools(mcp: FastMCP) -> None:
    """Register all tools with the FastMCP server."""

    @mcp.tool(
        description=(
            "Retrieve the authenticated user's recent Evergreen patches/commits "
            "with their CI/CD status. Use this to see your recent code changes, "
            "check patch status (success/failed/running), and identify patches "
            "that need attention. Returns patch IDs needed for other tools."
        )
    )
    async def list_user_recent_patches_evergreen(
        ctx: Context,
        project_id: Annotated[
            str | None,
            "Evergreen project identifier (e.g., 'mongodb-mongo-master', 'mms') to "
            "filter patches. If not provided, returns patches from all projects.",
        ] = None,
        limit: Annotated[
            int,
            "Number of recent patches to return. Use smaller numbers (3-5) for "
            "quick overview, larger (10-20) for comprehensive analysis. Maximum 50.",
        ] = 10,
    ) -> str:
        """List the user's recent patches from Evergreen."""
        evg_ctx = ctx.request_context.lifespan_context

        # Use default project ID if not provided
        effective_project_id = project_id or evg_ctx.default_project_id

        if effective_project_id:
            logger.info("Using project ID: %s", effective_project_id)

        result = await fetch_user_recent_patches(
            evg_ctx.client,
            evg_ctx.user_id,
            limit,
            project_id=effective_project_id,
        )
        return json.dumps(result, indent=2)

    @mcp.tool(
        description=(
            "Analyze failed CI/CD jobs for a specific patch to understand why "
            "builds are failing. Shows detailed failure information including "
            "failed tasks, build variants, timeout issues, log links, and test "
            "failure counts. Essential for debugging patch failures."
        )
    )
    async def get_patch_failed_jobs_evergreen(
        ctx: Context,
        patch_id: Annotated[
            str,
            "Patch identifier obtained from list_user_recent_patches. This is the "
            "'patch_id' field from the patches array.",
        ],
        project_id: Annotated[
            str | None,
            "Evergreen project identifier for the patch (e.g., 'mongodb-mongo-master', 'mms').",
        ] = None,
        max_results: Annotated[
            int,
            "Maximum number of failed tasks to analyze. Use 10-20 for focused "
            "analysis, 50+ for comprehensive failure review.",
        ] = 50,
    ) -> str:
        """Get failed jobs for a specific patch."""
        evg_ctx = ctx.request_context.lifespan_context

        # Use default project ID if not provided
        effective_project_id = project_id or evg_ctx.default_project_id

        result = await fetch_patch_failed_jobs(
            evg_ctx.client, patch_id, max_results, project_id=effective_project_id
        )
        return json.dumps(result, indent=2)

    @mcp.tool(
        description=(
            "Extract detailed logs from a specific failed Evergreen task to "
            "identify root cause of failures. Filters for error messages by "
            "default to focus on relevant failure information. Use task_id "
            "from get_patch_failed_jobs results."
        )
    )
    async def get_task_logs_evergreen(
        ctx: Context,
        task_id: Annotated[
            str,
            "Task identifier from get_patch_failed_jobs response. Found in the "
            "'task_id' field of failed_tasks array.",
        ],
        execution: Annotated[
            int,
            "Task execution number if task was retried. Usually 0 for first "
            "execution, 1+ for retries.",
        ] = 0,
        max_lines: Annotated[
            int,
            "Maximum log lines to return. Use 100-500 for quick error analysis, "
            "1000+ for comprehensive debugging.",
        ] = 1000,
        filter_errors: Annotated[
            bool,
            "Whether to show only error/failure messages (recommended) or all "
            "log output. Set to false only when you need complete context.",
        ] = True,
    ) -> str:
        """Get detailed logs for a specific task."""
        evg_ctx = ctx.request_context.lifespan_context

        arguments = {
            "task_id": task_id,
            "execution": execution,
            "max_lines": max_lines,
            "filter_errors": filter_errors,
        }

        result = await fetch_task_logs(evg_ctx.client, arguments)
        return json.dumps(result, indent=2)

    @mcp.tool(
        description=(
            "Fetch detailed test results for a specific Evergreen task, "
            "including individual unit test failures. Use this when a task "
            "shows failed_test_count > 0 to get specific test failure "
            "details. Essential for debugging unit test failures."
        )
    )
    async def get_task_test_results_evergreen(
        ctx: Context,
        task_id: Annotated[
            str,
            "Task identifier from get_patch_failed_jobs response. Found in the "
            "'task_id' field of failed_tasks array.",
        ],
        execution: Annotated[
            int,
            "Task execution number if task was retried. Usually 0 for first "
            "execution, 1+ for retries.",
        ] = 0,
        failed_only: Annotated[
            bool,
            "Whether to fetch only failed tests (recommended) or all test results. "
            "Set to false to see all tests including passing ones.",
        ] = True,
        limit: Annotated[
            int,
            "Maximum number of test results to return. Use 50-100 for focused "
            "analysis, 200+ for comprehensive review.",
        ] = 100,
    ) -> str:
        """Get detailed test results for a specific task."""
        evg_ctx = ctx.request_context.lifespan_context

        arguments = {
            "task_id": task_id,
            "execution": execution,
            "failed_only": failed_only,
            "limit": limit,
        }

        result = await fetch_task_test_results(evg_ctx.client, arguments)
        return json.dumps(result, indent=2)
    
    @mcp.tool(
        description=(
            "Retrieve recent versions (flattened waterfall view) containing failed tasks "
            "for one or more build variants in a project. Use this to identify the most "
            "recent failing revisions and obtain task IDs for deeper log/test analysis."
        )
    )
    async def get_waterfall_failed_tasks_evergreen(
        ctx: Context,
        project_identifier: Annotated[
            str,
            "Evergreen project identifier (e.g. 'mms'). Required.",
        ],
        variant: Annotated[
            str | None,
            "Single build variant to query (e.g. 'ACPerf'). Can be combined with 'variants' list.",
        ] = None,
        variants: Annotated[
            list[str] | None,
            "List of build variants to query. Provide multiple variants when investigating failures across platforms.",
        ] = None,
        waterfall_limit: Annotated[
            int,
            "Maximum number of recent flattened versions to examine from the waterfall. Limits versions, not tasks. Defaults to 200.",
        ] = 200,
        statuses: Annotated[
            list[str] | None,
            "Task statuses to include. Defaults to ['failed','system-failed','task-timed-out']. You may also include setup-failed",
        ] = None,
    ) -> str:
        """Get flattened waterfall recent versions containing failed tasks."""
        evg_ctx = ctx.request_context.lifespan_context

        # merge variant(s) into a deduplicated list
        variant_set: set[str] = set()
        if variant:
            variant_set.add(variant)
        if variants:
            variant_set.update(variants)
        variant_list = list(variant_set) if variant_set else None

        effective_statuses = statuses or ["failed", "system-failed", "task-timed-out"]

        arguments = {
            "project_identifier": project_identifier,
            "variants": variant_list,
            "waterfall_limit": waterfall_limit,
            "statuses": effective_statuses,
        }

        result = await fetch_waterfall_failed_tasks(evg_ctx.client, arguments)
        return json.dumps(result, indent=2)

    @mcp.tool(
        description=(
            "Download artifacts from a specific Evergreen task. Use this to retrieve "
            "build outputs, test results, logs, or other files generated by a task. "
            "Artifacts are downloaded to a local directory structure organized by version."
        )
    )
    async def download_task_artifacts_evergreen(
        ctx: Context,
        task_id: Annotated[
            str,
            "The ID of the task to download artifacts for. Required.",
        ],
        artifact_filter: Annotated[
            str | None,
            "Optional filter to download only artifacts containing this string (case-insensitive). If not provided, all artifacts are downloaded.",
        ] = None,
        work_dir: Annotated[
            str,
            "The base directory to create artifact folders in. Defaults to 'WORK'.",
        ] = "WORK",
    ) -> str:
        """Download artifacts for a given Evergreen task and return paths."""
        evg_ctx = ctx.request_context.lifespan_context

        # call download function (synchronous in current codebase)
        result = download_task_artifacts(
            task_id=task_id, artifact_filter=artifact_filter, work_dir=work_dir
        )

        # convert Path objects to strings for JSON serialization
        serializable_result = {name: str(path) for name, path in result.items()}

        response = {
            "task_id": task_id,
            "artifact_filter": artifact_filter,
            "work_dir": work_dir,
            "downloaded_artifacts": serializable_result,
            "artifact_count": len(serializable_result),
        }

        return json.dumps(response, indent=2)


    logger.info("Registered %d tools with FastMCP server why", 600)


async def handle_list_user_recent_patches(
    arguments: Dict[str, Any], client, user_id: str
) -> Sequence[types.TextContent]:
    """Handle list_user_recent_patches_evergreen tool call"""
    try:
        limit = arguments.get("limit", 10)
        result = await fetch_user_recent_patches(client, user_id, limit)
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        logger.error("Failed to fetch user patches: %s", e)
        error_response = {
            "error": str(e),
            "tool": "list_user_recent_patches_evergreen",
            "arguments": arguments,
        }
        return [
            types.TextContent(type="text", text=json.dumps(error_response, indent=2))
        ]


async def handle_get_patch_failed_jobs(
    arguments: Dict[str, Any], client
) -> Sequence[types.TextContent]:
    """Handle get_patch_failed_jobs_evergreen tool call"""
    try:
        patch_id = arguments.get("patch_id")
        if not patch_id:
            raise ValueError("patch_id parameter is required")

        max_results = arguments.get("max_results", 50)
        result = await fetch_patch_failed_jobs(client, patch_id, max_results)
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        logger.error("Failed to fetch patch failed jobs: %s", e)
        error_response = {
            "error": str(e),
            "tool": "get_patch_failed_jobs_evergreen",
            "arguments": arguments,
        }
        return [
            types.TextContent(type="text", text=json.dumps(error_response, indent=2))
        ]


async def handle_get_task_logs(
    arguments: Dict[str, Any], client
) -> Sequence[types.TextContent]:
    """Handle get_task_logs_evergreen tool call"""
    try:
        result = await fetch_task_logs(client, arguments)
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        logger.error("Failed to fetch task logs: %s", e)
        error_response = {
            "error": str(e),
            "tool": "get_task_logs_evergreen",
            "arguments": arguments,
        }
        return [
            types.TextContent(type="text", text=json.dumps(error_response, indent=2))
        ]


async def handle_get_task_test_results(
    arguments: Dict[str, Any], client
) -> Sequence[types.TextContent]:
    """Handle get_task_test_results_evergreen tool call"""
    try:
        result = await fetch_task_test_results(client, arguments)
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        logger.error("Failed to fetch task test results: %s", e)
        error_response = {
            "error": str(e),
            "tool": "get_task_test_results_evergreen",
            "arguments": arguments,
        }
        return [
            types.TextContent(type="text", text=json.dumps(error_response, indent=2))
        ]


async def handle_get_waterfall_failed_tasks(
    arguments: Dict[str, Any], client
) -> Sequence[types.TextContent]:
    """Handle get_waterfall_failed_tasks_evergreen tool call"""
    try:
        result = await fetch_waterfall_failed_tasks(client, arguments)
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        logger.error("Failed to fetch waterfall failed tasks: %s", e)
        error_response = {
            "error": str(e),
            "tool": "get_waterfall_failed_tasks_evergreen",
            "arguments": arguments,
        }
        return [
            types.TextContent(type="text", text=json.dumps(error_response, indent=2))
        ]


async def handle_download_task_artifacts(
    arguments: Dict[str, Any], client
) -> Sequence[types.TextContent]:
    """Handle download_task_artifacts_evergreen tool call"""
    try:
        task_id = arguments.get("task_id")
        if not task_id:
            raise ValueError("task_id parameter is required")

        artifact_filter = arguments.get("artifact_filter")
        work_dir = arguments.get("work_dir", "WORK")

        # Call the download function
        result = download_task_artifacts(
            task_id=task_id,
            artifact_filter=artifact_filter,
            work_dir=work_dir,
        )

        # Convert Path objects to strings for JSON serialization
        serializable_result = {}
        for artifact_name, path in result.items():
            serializable_result[artifact_name] = str(path)

        response = {
            "task_id": task_id,
            "artifact_filter": artifact_filter,
            "work_dir": work_dir,
            "downloaded_artifacts": serializable_result,
            "artifact_count": len(serializable_result),
        }

        return [types.TextContent(type="text", text=json.dumps(response, indent=2))]
    except Exception as e:
        logger.error("Failed to download task artifacts: %s", e)
        error_response = {
            "error": str(e),
            "tool": "download_task_artifacts_evergreen",
            "arguments": arguments,
        }
        return [
            types.TextContent(type="text", text=json.dumps(error_response, indent=2))
        ]
