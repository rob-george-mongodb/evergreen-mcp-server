"""CLI for restarting Evergreen tasks."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Sequence

import aiohttp


class CLIError(Exception):
    """User-facing CLI validation error."""

    def __init__(self, message: str, exit_code: int = 2):
        super().__init__(message)
        self.exit_code = exit_code


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CLIError(message)


@dataclass(frozen=True)
class RestartRequest:
    dry_run: bool
    base_url: str = "https://evergreen.corp.mongodb.com/rest/v2"


@dataclass(frozen=True)
class TaskRestart:
    task_name: str
    task_id: str
    variant: str
    consecutive_failure_count: int


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="evergreen-restart-tasks")
    parser.add_argument(
        "--dryRun", action="store_true", help="Print actions without executing"
    )
    parser.add_argument(
        "--baseUrl",
        default="https://evergreen.corp.mongodb.com/rest/v2",
        help="Evergreen REST API base URL",
    )
    return parser


def parse_request(argv: Sequence[str] | None = None) -> RestartRequest:
    parser = build_parser()
    args = parser.parse_args(argv)
    return RestartRequest(dry_run=args.dryRun, base_url=args.baseUrl.rstrip("/"))


def extract_task_id_from_url(url: str) -> str:
    """Extract task_id from Evergreen task URL.

    Args:
        url: Evergreen task URL like https://evergreen.mongodb.com/task/{task_id}

    Returns:
        Task ID string

    Raises:
        CLIError: If URL format is invalid
    """
    parts = url.rstrip("/").split("/")
    if len(parts) < 2 or parts[-2] != "task":
        raise CLIError(f"Invalid task URL format: {url}")
    return parts[-1]


def parse_task_restarts_from_stdin() -> list[TaskRestart]:
    """Parse JSON input from stdin.

    Expects full JSON object with 'streaks' array from waterfall triage output.

    Returns:
        List of TaskRestart objects

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
        raise CLIError("Input must contain 'streaks' array from waterfall triage output")

    return _parse_streaks_format(full_obj)


def _parse_streaks_format(data: dict[str, Any]) -> list[TaskRestart]:
    """Parse streaks format from waterfall triage output.

    Extracts latest_failure from each streak.

    Args:
        data: Full JSON object with 'streaks' array

    Returns:
        List of TaskRestart objects
    """
    restarts: list[TaskRestart] = []

    streaks = data.get("streaks", [])
    for idx, streak in enumerate(streaks):
        try:
            task_name = streak["task_name"]
            variant = streak.get("variant", "unknown")
            consecutive_failure_count = streak.get("consecutive_failure_count", 0)

            latest_failure = streak.get("latest_failure", {})
            task_id = latest_failure.get("task_id")

            if not task_id:
                latest_url = latest_failure.get("task_url")
                if latest_url:
                    task_id = extract_task_id_from_url(latest_url)
                else:
                    raise CLIError(f"Streak {idx}: Missing task_id in latest_failure")

            restarts.append(
                TaskRestart(
                    task_name=task_name,
                    task_id=task_id,
                    variant=variant,
                    consecutive_failure_count=consecutive_failure_count,
                )
            )
        except KeyError as e:
            raise CLIError(f"Streak {idx}: Missing required field: {e}") from e
        except CLIError:
            raise

    return restarts


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


async def restart_task(
    task: TaskRestart,
    token: str,
    base_url: str,
    dry_run: bool,
) -> dict[str, Any]:
    """Restart a single task via REST API.

    Args:
        task: Task to restart
        token: OAuth bearer token
        base_url: Evergreen REST API base URL
        dry_run: If True, don't actually restart

    Returns:
        Result dict with task_name, task_id, success, and optional error
    """
    result = {
        "task_name": task.task_name,
        "task_id": task.task_id,
        "variant": task.variant,
        "consecutive_failure_count": task.consecutive_failure_count,
        "success": False,
    }

    if dry_run:
        result["success"] = True
        result["dry_run"] = True
        return result

    url = f"{base_url}/tasks/{task.task_id}/restart"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers) as response:
                if response.status == 200:
                    result["success"] = True
                else:
                    text = await response.text()
                    result["error"] = f"HTTP {response.status}: {text}"
    except Exception as e:
        result["error"] = str(e)

    return result


async def run_restarts(request: RestartRequest) -> dict[str, Any]:
    """Execute restart operations for all tasks from stdin.

    Args:
        request: Restart request configuration

    Returns:
        Summary dict with results for each task
    """
    tasks = parse_task_restarts_from_stdin()

    if not tasks:
        return {"tasks": [], "summary": {"total": 0, "success": 0, "failed": 0}}

    if request.dry_run:
        token = "dry-run-token"
    else:
        token = get_oauth_token()

    results = []
    for task in tasks:
        result = await restart_task(
            task=task,
            token=token,
            base_url=request.base_url,
            dry_run=request.dry_run,
        )
        results.append(result)

    success_count = sum(1 for r in results if r["success"])
    failed_count = len(results) - success_count

    return {
        "tasks": results,
        "summary": {
            "total": len(results),
            "success": success_count,
            "failed": failed_count,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    try:
        request = parse_request(argv)
        result = asyncio.run(run_restarts(request))
        json.dump(result, sys.stdout)
        sys.stdout.write("\n")
        return 0 if result["summary"]["failed"] == 0 else 1
    except CLIError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
