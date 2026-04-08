"""Standalone CLI for Evergreen waterfall triage."""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import sys
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Sequence, Union

from evergreen_waterfall_triage.analysis import run_current_streak_triage
from evergreen_waterfall_triage.auth import graphql_client_context


class CLIError(Exception):
    """User-facing CLI validation error."""

    def __init__(self, message: str, exit_code: int = 2):
        super().__init__(message)
        self.exit_code = exit_code


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CLIError(message)


@dataclass(frozen=True)
class TriageRequest:
    project_identifier: str
    variants: list[str]
    waterfall_limit: int = 200
    min_num_consecutive_failures: int = 1


TriageRunner = Callable[
    [TriageRequest], Union[dict[str, Any], Awaitable[dict[str, Any]]]
]


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="evergreen-waterfall-triage")
    parser.add_argument("--projectIdentifier", required=True)
    parser.add_argument("--variant", action="append", default=[])
    parser.add_argument(
        "--variants",
        nargs="+",
        default=[],
        help="Space- or comma-separated list of variants.",
    )
    parser.add_argument("--waterfallLimit", type=int, default=200)
    parser.add_argument("--minNumConsecutiveFailures", type=int, default=1)
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


def parse_request(argv: Sequence[str] | None = None) -> TriageRequest:
    parser = build_parser()
    args = parser.parse_args(argv)

    variants = _deduplicate(
        _split_variant_values(args.variant) + _split_variant_values(args.variants)
    )
    if not variants:
        raise CLIError("At least one variant must be provided")
    if args.waterfallLimit < 1:
        raise CLIError("--waterfallLimit must be >= 1")
    if args.minNumConsecutiveFailures < 1:
        raise CLIError("--minNumConsecutiveFailures must be >= 1")

    return TriageRequest(
        project_identifier=args.projectIdentifier,
        variants=variants,
        waterfall_limit=args.waterfallLimit,
        min_num_consecutive_failures=args.minNumConsecutiveFailures,
    )


async def run_triage(request: TriageRequest) -> dict[str, Any]:
    """Integration point for the package's waterfall triage implementation."""

    async with graphql_client_context() as context:
        return await run_current_streak_triage(
            client=context.client,
            project_identifier=request.project_identifier,
            variants=request.variants,
            waterfall_limit=request.waterfall_limit,
            min_num_consecutive_failures=request.min_num_consecutive_failures,
        )


def _run_runner(
    runner: TriageRunner,
    request: TriageRequest,
) -> dict[str, Any]:
    result = runner(request)
    if inspect.isawaitable(result):
        return asyncio.run(result)
    return result


def main(argv: Sequence[str] | None = None, runner: TriageRunner | None = None) -> int:
    try:
        request = parse_request(argv)
        result = _run_runner(runner or run_triage, request)
        json.dump(result, sys.stdout)
        sys.stdout.write("\n")
        return 0
    except CLIError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
