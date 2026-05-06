"""CLI for adding tasks to an Evergreen patch from waterfall triage output."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Sequence

import aiohttp

from .patch_api import PatchAddTasksRequest, VariantTasks, add_tasks_to_patch


class CLIError(Exception):
    """User-facing CLI validation error."""

    def __init__(self, message: str, exit_code: int = 2):
        super().__init__(message)
        self.exit_code = exit_code


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CLIError(message)


@dataclass(frozen=True)
class CLIRequest:
    """CLI request configuration."""

    patch_id: str
    dry_run: bool
    base_url: str = "https://evergreen.corp.mongodb.com/rest/v2"


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="evergreen-add-patch-tasks")
    parser.add_argument(
        "--patchId",
        required=True,
        help="Patch ID to add tasks to",
    )
    parser.add_argument(
        "--dryRun",
        action="store_true",
        help="Print actions without executing",
    )
    parser.add_argument(
        "--baseUrl",
        default="https://evergreen.corp.mongodb.com/rest/v2",
        help="Evergreen REST API base URL",
    )
    return parser


def parse_request(argv: Sequence[str] | None = None) -> CLIRequest:
    parser = build_parser()
    args = parser.parse_args(argv)
    return CLIRequest(
        patch_id=args.patchId,
        dry_run=args.dryRun,
        base_url=args.baseUrl.rstrip("/"),
    )


def parse_waterfall_triage_from_stdin() -> list[VariantTasks]:
    """Parse JSON input from stdin.

    Expects full JSON object with 'streaks' array from waterfall triage output.
    Filters out failures where the actual variant ends with '_generated'.

    Returns:
        List of VariantTasks objects grouped by variant

    Raises:
        CLIError: If input is invalid
    """
    stdin_text = sys.stdin.read().strip()
    if not stdin_text:
        return []

    try:
        full_obj = json.loads(stdin_text)
    except json.JSONDecodeError as e:
        raise CLIError(f"Invalid JSON: {e}") from e

    if "streaks" not in full_obj:
        raise CLIError(
            "Input must contain 'streaks' array from waterfall triage output"
        )

    return _parse_streaks_format(full_obj)


def _parse_streaks_format(data: dict[str, Any]) -> list[VariantTasks]:
    """Parse streaks format from waterfall triage output.

    Groups tasks by their actual variant (the_variant field), filtering out
    variants ending with '_generated'.

    Args:
        data: Full JSON object with 'streaks' array

    Returns:
        List of VariantTasks objects grouped by variant
    """
    variant_tasks_map: dict[str, set[str]] = {}

    streaks = data.get("streaks", [])
    for streak in streaks:
        latest_failure = streak.get("latest_failure", {})
        actual_variant = latest_failure.get(
            "the_actual_variant_we_should_stop_using_the_incomprehensible_display_name_ones"
        )

        if not actual_variant:
            continue

        if actual_variant.endswith("_generated"):
            continue

        task_name = streak.get("task_name")
        if not task_name:
            continue

        if actual_variant not in variant_tasks_map:
            variant_tasks_map[actual_variant] = set()

        variant_tasks_map[actual_variant].add(task_name)

    return [
        VariantTasks(variant=variant, tasks=sorted(tasks))
        for variant, tasks in sorted(variant_tasks_map.items())
    ]


def get_oauth_token() -> str:
    """Get OAuth token from evergreen CLI.

    Returns:
        OAuth bearer token string

    Raises:
        CLIError: If token retrieval fails
    """
    try:
        result = subprocess.run(
            ["evergreen", "client", "get-oauth-token"],
            capture_output=True,
            text=True,
            check=True,
        )
        token = result.stdout.strip()
        if not token:
            raise CLIError("evergreen client get-oauth-token returned empty token")
        return token
    except FileNotFoundError as e:
        raise CLIError(
            "evergreen CLI not found. Please install the evergreen CLI tool."
        ) from e
    except subprocess.CalledProcessError as e:
        raise CLIError(f"evergreen client get-oauth-token failed: {e.stderr}") from e


async def run_cli(request: CLIRequest) -> dict[str, Any]:
    """Execute patch task additions for all tasks from stdin.

    Args:
        request: CLI request configuration

    Returns:
        Summary dict with results for each variant
    """
    variant_tasks = parse_waterfall_triage_from_stdin()

    if not variant_tasks:
        return {
            "patch_id": request.patch_id,
            "variant_tasks": [],
            "summary": {"total": 0, "success": 0, "failed": 0},
        }

    if request.dry_run:
        token = "dry-run-token"
    else:
        token = get_oauth_token()

    patch_request = PatchAddTasksRequest(
        patch_id=request.patch_id,
        variant_tasks=variant_tasks,
        dry_run=request.dry_run,
        base_url=request.base_url,
    )

    return await add_tasks_to_patch(patch_request, token)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        request = parse_request(argv)
        result = asyncio.run(run_cli(request))
        json.dump(result, sys.stdout)
        sys.stdout.write("\n")
        return 0 if result["summary"]["failed"] == 0 else 1
    except CLIError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
