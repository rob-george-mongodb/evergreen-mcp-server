"""CLI for launching and cleaning up per-failure E2E investigations."""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Sequence, Union

from evergreen_waterfall_triage import cli as triage_cli
from evergreen_waterfall_triage.investigation import (
    CommandRunner,
    cleanup_investigations,
    parse_triage_report,
    run_command,
    run_investigations,
)


class CLIError(Exception):
    """User-facing CLI validation error."""

    def __init__(self, message: str, exit_code: int = 2):
        super().__init__(message)
        self.exit_code = exit_code


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CLIError(message)


@dataclass(frozen=True)
class InvestigationRequest:
    mode: str
    triage_json_path: str | None
    target_repo_path: str
    worktree_root: str | None
    agent: str
    opencode_bin: str
    opencode_mode: str
    opencode_attach_url: str | None
    jobs: int
    dry_run: bool
    remove_branches: bool = False
    triage_request: triage_cli.TriageRequest | None = None


TriageRunner = Callable[
    [triage_cli.TriageRequest],
    Union[dict[str, Any], Awaitable[dict[str, Any]]],
]


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="evergreen-waterfall-investigate")
    subparsers = parser.add_subparsers(dest="command")

    launch_parser = subparsers.add_parser("launch")
    launch_parser.add_argument("--triageJson")
    launch_parser.add_argument("--projectIdentifier")
    launch_parser.add_argument("--variant", action="append", default=[])
    launch_parser.add_argument(
        "--variants",
        nargs="+",
        default=[],
        help="Space- or comma-separated list of variants.",
    )
    launch_parser.add_argument("--waterfallLimit", type=int)
    launch_parser.add_argument("--minNumConsecutiveFailures", type=int)
    launch_parser.add_argument("--targetRepoPath", required=True)
    launch_parser.add_argument("--worktreeRoot")
    launch_parser.add_argument("--agent", default="nds-e2e-investigator")
    launch_parser.add_argument("--opencodeBin", default="opencode")
    launch_parser.add_argument(
        "--opencodeMode",
        choices=["auto", "attach", "local"],
        default="auto",
    )
    launch_parser.add_argument("--opencodeAttachUrl")
    launch_parser.add_argument("--jobs", type=int, default=1)
    launch_parser.add_argument("--dryRun", action="store_true")

    cleanup_parser = subparsers.add_parser("cleanup")
    cleanup_parser.add_argument("--targetRepoPath", required=True)
    cleanup_parser.add_argument("--worktreeRoot")
    cleanup_parser.add_argument("--removeBranches", action="store_true")
    cleanup_parser.add_argument("--dryRun", action="store_true")
    return parser


def _split_variant_values(values: Sequence[str]) -> list[str]:
    variants: list[str] = []
    for value in values:
        for item in value.split(","):
            normalized = item.strip()
            if normalized:
                variants.append(normalized)
    return variants


def _deduplicate(values: Sequence[str]) -> list[str]:
    deduplicated: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            deduplicated.append(value)
            seen.add(value)
    return deduplicated


def parse_request(argv: Sequence[str] | None = None) -> InvestigationRequest:
    parser = build_parser()
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    if raw_argv and raw_argv[0].startswith("-"):
        raw_argv = ["launch", *raw_argv]
    args = parser.parse_args(raw_argv)

    if not args.command:
        raise CLIError("A subcommand is required: launch or cleanup")

    if args.command == "cleanup":
        return InvestigationRequest(
            mode="cleanup",
            triage_json_path=None,
            target_repo_path=args.targetRepoPath,
            worktree_root=args.worktreeRoot,
            agent="nds-e2e-investigator",
            opencode_bin="opencode",
            opencode_mode="auto",
            opencode_attach_url=None,
            jobs=1,
            dry_run=args.dryRun,
            remove_branches=args.removeBranches,
        )

    variants = _deduplicate(
        _split_variant_values(args.variant) + _split_variant_values(args.variants)
    )
    if args.jobs < 1:
        raise CLIError("--jobs must be >= 1")

    if args.triageJson:
        if args.projectIdentifier or variants:
            raise CLIError("Provide either --triageJson or live query arguments, not both")
        if args.waterfallLimit is not None or args.minNumConsecutiveFailures is not None:
            raise CLIError("Provide either --triageJson or live query arguments, not both")
        return InvestigationRequest(
            mode="launch",
            triage_json_path=args.triageJson,
            target_repo_path=args.targetRepoPath,
            worktree_root=args.worktreeRoot,
            agent=args.agent,
            opencode_bin=args.opencodeBin,
            opencode_mode=args.opencodeMode,
            opencode_attach_url=args.opencodeAttachUrl,
            jobs=args.jobs,
            dry_run=args.dryRun,
        )

    if not args.projectIdentifier:
        raise CLIError("--projectIdentifier is required when --triageJson is not provided")
    if not variants:
        raise CLIError("At least one variant must be provided")

    waterfall_limit = args.waterfallLimit if args.waterfallLimit is not None else 200
    min_failures = (
        args.minNumConsecutiveFailures
        if args.minNumConsecutiveFailures is not None
        else 1
    )
    if waterfall_limit < 1:
        raise CLIError("--waterfallLimit must be >= 1")
    if min_failures < 1:
        raise CLIError("--minNumConsecutiveFailures must be >= 1")

    return InvestigationRequest(
        mode="launch",
        triage_json_path=None,
        target_repo_path=args.targetRepoPath,
        worktree_root=args.worktreeRoot,
        agent=args.agent,
        opencode_bin=args.opencodeBin,
        opencode_mode=args.opencodeMode,
        opencode_attach_url=args.opencodeAttachUrl,
        jobs=args.jobs,
        dry_run=args.dryRun,
        triage_request=triage_cli.TriageRequest(
            project_identifier=args.projectIdentifier,
            variants=variants,
            waterfall_limit=waterfall_limit,
            min_num_consecutive_failures=min_failures,
        ),
    )


def _run_runner(
    runner: TriageRunner,
    request: triage_cli.TriageRequest,
) -> dict[str, Any]:
    result = runner(request)
    if inspect.isawaitable(result):
        return asyncio.run(result)
    return result


def _read_triage_report(path: str) -> dict[str, Any]:
    if path == "-":
        return json.load(sys.stdin)

    resolved_path = Path(path).expanduser().resolve()
    with resolved_path.open() as handle:
        return json.load(handle)


def main(
    argv: Sequence[str] | None = None,
    triage_runner: TriageRunner | None = None,
    command_runner: CommandRunner = run_command,
) -> int:
    try:
        request = parse_request(argv)
        if request.mode == "cleanup":
            result = cleanup_investigations(
                target_repo_path=request.target_repo_path,
                worktree_root=request.worktree_root,
                remove_branches=request.remove_branches,
                dry_run=request.dry_run,
                runner=command_runner,
            )
            json.dump(result, sys.stdout)
            sys.stdout.write("\n")
            return 0

        if request.triage_json_path is not None:
            report = _read_triage_report(request.triage_json_path)
        else:
            assert request.triage_request is not None
            report = _run_runner(triage_runner or triage_cli.run_triage, request.triage_request)

        targets = parse_triage_report(report)
        result = run_investigations(
            targets,
            target_repo_path=request.target_repo_path,
            worktree_root=request.worktree_root,
            agent=request.agent,
            opencode_bin=request.opencode_bin,
            opencode_mode=request.opencode_mode,
            opencode_attach_url=request.opencode_attach_url,
            jobs=request.jobs,
            dry_run=request.dry_run,
            runner=command_runner,
        )
        json.dump(result, sys.stdout)
        sys.stdout.write("\n")
        return 0
    except (CLIError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return getattr(exc, "exit_code", 1)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
