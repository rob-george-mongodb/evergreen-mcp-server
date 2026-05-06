"""CLI for adding specific variant tasks to an existing patch."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Sequence

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
    variant: str
    tasks: Sequence[str]
    dry_run: bool
    base_url: str = "https://evergreen.corp.mongodb.com/rest/v2"


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="evergreen-add-variant-tasks")
    parser.add_argument(
        "--patchId",
        required=True,
        help="Patch ID to add tasks to",
    )
    parser.add_argument(
        "--variant",
        required=True,
        help="Variant name to add tasks to",
    )
    parser.add_argument(
        "tasks",
        nargs="+",
        help="Task names to add to the patch",
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
        variant=args.variant,
        tasks=args.tasks,
        dry_run=args.dryRun,
        base_url=args.baseUrl.rstrip("/"),
    )


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


async def run_cli(request: CLIRequest) -> dict:
    """Execute patch task addition for specified variant and tasks.

    Args:
        request: CLI request configuration

    Returns:
        Summary dict with results
    """
    if request.dry_run:
        token = "dry-run-token"
    else:
        token = get_oauth_token()

    patch_request = PatchAddTasksRequest(
        patch_id=request.patch_id,
        variant_tasks=[VariantTasks(variant=request.variant, tasks=request.tasks)],
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
