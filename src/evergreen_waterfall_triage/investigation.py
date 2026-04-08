"""Launch and clean up E2E investigations from waterfall triage output."""

from __future__ import annotations

import hashlib
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


@dataclass(frozen=True)
class InvestigationTarget:
    variant: str
    task_name: str
    task_url: str
    revision: str | None = None
    branch: str | None = None


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[Sequence[str], Path | None], CommandResult]
MANAGED_BRANCH_PREFIX = "ai/evergreen/"
SESSION_NOT_FOUND_TEXT = "Session not found"


def run_command(command: Sequence[str], cwd: Path | None = None) -> CommandResult:
    completed = subprocess.run(
        list(command),
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        check=False,
    )
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def parse_triage_report(report: Mapping[str, Any]) -> list[InvestigationTarget]:
    raw_streaks = report.get("streaks")
    if not isinstance(raw_streaks, list):
        raise ValueError("triage report must include a 'streaks' list")

    targets: list[InvestigationTarget] = []
    for index, streak in enumerate(raw_streaks):
        if not isinstance(streak, Mapping):
            raise ValueError(f"streak {index} must be an object")

        variant = streak.get("variant")
        task_name = streak.get("task_name")
        latest_failure = streak.get("latest_failure")
        if not isinstance(variant, str) or not variant:
            raise ValueError(f"streak {index} is missing a valid 'variant'")
        if not isinstance(task_name, str) or not task_name:
            raise ValueError(f"streak {index} is missing a valid 'task_name'")
        if not isinstance(latest_failure, Mapping):
            raise ValueError(f"streak {index} is missing 'latest_failure'")

        task_url = latest_failure.get("task_url")
        if not isinstance(task_url, str) or not task_url:
            raise ValueError(
                f"streak {index} latest_failure is missing a valid 'task_url'"
            )

        revision = latest_failure.get("revision")
        branch = latest_failure.get("branch")
        targets.append(
            InvestigationTarget(
                variant=variant,
                task_name=task_name,
                task_url=task_url,
                revision=revision if isinstance(revision, str) and revision else None,
                branch=branch if isinstance(branch, str) and branch else None,
            )
        )

    return targets


def safe_report_filename(task_name: str) -> str:
    return f"{task_name.replace('/', '_').replace('\\', '_')}.md"


def build_investigation_prompt(
    target: InvestigationTarget,
    report_filename: str,
) -> str:
    return (
        f"Hey AI investigate the E2E failure in {target.task_url}. "
        f"Write your report up in your working directory as {report_filename}."
    )


def build_opencode_command(
    *,
    opencode_bin: str,
    worktree_path: Path,
    agent: str,
    prompt: str,
    opencode_mode: str,
    opencode_attach_url: str | None,
) -> list[str]:
    command = [opencode_bin, "run"]
    if opencode_mode == "attach":
        if not opencode_attach_url:
            raise ValueError("opencode attach mode requires an attach URL")
        command.extend(["--attach", opencode_attach_url])
    command.extend(["--agent", agent, "--dir", str(worktree_path), prompt])
    return command


def is_session_not_found_error(result: CommandResult) -> bool:
    combined = f"{result.stdout}\n{result.stderr}"
    return SESSION_NOT_FOUND_TEXT in combined


def describe_opencode_failure(result: CommandResult, *, attempted_mode: str) -> tuple[str, str]:
    if is_session_not_found_error(result):
        if attempted_mode == "attach":
            return (
                "session_create_failed",
                "opencode could not create a session via the attached server; the server may not be able to resolve or initialize the provided --dir",
            )
        return (
            "session_create_failed",
            "opencode could not create a local session in the fresh worktree",
        )
    return (
        "opencode_failed",
        result.stderr.strip() or "opencode run failed",
    )


def _resolve_opencode_modes(
    *,
    opencode_mode: str,
    opencode_attach_url: str | None,
) -> list[str]:
    if opencode_mode not in {"auto", "attach", "local"}:
        raise ValueError("opencode_mode must be one of: auto, attach, local")
    if opencode_mode == "auto":
        return ["attach", "local"] if opencode_attach_url else ["local"]
    if opencode_mode == "attach" and not opencode_attach_url:
        raise ValueError("attach mode requires --opencodeAttachUrl")
    return [opencode_mode]


def _slugify(value: str, *, max_length: int) -> str:
    cleaned = []
    previous_was_dash = False
    for char in value.lower():
        if char.isalnum():
            cleaned.append(char)
            previous_was_dash = False
            continue
        if previous_was_dash:
            continue
        cleaned.append("-")
        previous_was_dash = True

    slug = "".join(cleaned).strip("-") or "item"
    return slug[:max_length].rstrip("-") or "item"


def _target_suffix(target: InvestigationTarget) -> str:
    revision_prefix = _slugify(target.revision or "head", max_length=8)
    digest = hashlib.sha1(
        f"{target.variant}\n{target.task_name}\n{target.task_url}".encode("utf-8")
    ).hexdigest()[:6]
    return f"{revision_prefix}-{digest}"


def build_branch_name(target: InvestigationTarget) -> str:
    variant_slug = _slugify(target.variant, max_length=40)
    task_slug = _slugify(target.task_name, max_length=60)
    return f"{MANAGED_BRANCH_PREFIX}{variant_slug}/{task_slug}-{_target_suffix(target)}"


def build_worktree_path(worktree_root: Path, target: InvestigationTarget) -> Path:
    variant_slug = _slugify(target.variant, max_length=40)
    task_slug = _slugify(target.task_name, max_length=80)
    return worktree_root / variant_slug / f"{task_slug}-{_target_suffix(target)}"


def resolve_repo_root(target_repo_path: str | Path, runner: CommandRunner) -> Path:
    repo_path = Path(target_repo_path).expanduser().resolve()
    if not repo_path.exists():
        raise ValueError(f"target repo path does not exist: {repo_path}")

    result = runner(["git", "rev-parse", "--show-toplevel"], repo_path)
    if result.returncode != 0:
        stderr = result.stderr.strip() or "not a git repository"
        raise ValueError(f"failed to resolve git repo root for {repo_path}: {stderr}")
    return Path(result.stdout.strip()).resolve()


def default_worktree_root(repo_root: Path) -> Path:
    return repo_root.parent / f"{repo_root.name}-investigations"


def _truncate_output(value: str, *, limit: int = 2000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "..."


def is_managed_branch_name(branch_name: str | None) -> bool:
    return isinstance(branch_name, str) and branch_name.startswith(MANAGED_BRANCH_PREFIX)


def parse_worktree_list_output(output: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                records.append(current)
                current = {}
            continue

        key, _, value = line.partition(" ")
        current[key] = value

    if current:
        records.append(current)
    return records


def find_untracked_markdown_files(
    worktree_path: Path,
    runner: CommandRunner,
) -> tuple[list[str], CommandResult | None]:
    result = runner(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        worktree_path,
    )
    if result.returncode != 0:
        return ([], result)

    markdown_files = sorted(
        line[3:].strip()
        for line in result.stdout.splitlines()
        if line.startswith("?? ") and line[3:].strip().lower().endswith(".md")
    )
    return (markdown_files, None)


def list_managed_branches(
    *,
    target_repo_path: str | Path,
    runner: CommandRunner = run_command,
) -> dict[str, Any]:
    repo_root = resolve_repo_root(target_repo_path, runner)
    result = runner(
        [
            "git",
            "for-each-ref",
            "--format=%(refname:short)",
            "refs/heads/ai/evergreen",
            "refs/heads/ai/evergreen/**",
        ],
        repo_root,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or "git for-each-ref failed"
        raise ValueError(stderr)

    branches = sorted(
        branch.strip()
        for branch in result.stdout.splitlines()
        if is_managed_branch_name(branch.strip())
    )
    return {
        "repo_root": repo_root,
        "branches": branches,
    }


def _managed_worktree_record_for_branch(
    branch_name: str,
    active_worktrees: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    active = active_worktrees.get(branch_name)
    if active is not None:
        return dict(active)
    return {
        "path": None,
        "branch_name": branch_name,
        "head": None,
        "locked": False,
        "prunable": False,
        "has_worktree": False,
        "orphan_branch": True,
    }


def list_managed_worktrees(
    *,
    target_repo_path: str | Path,
    worktree_root: str | Path | None = None,
    runner: CommandRunner = run_command,
) -> dict[str, Any]:
    repo_root = resolve_repo_root(target_repo_path, runner)
    resolved_worktree_root = (
        Path(worktree_root).expanduser().resolve()
        if worktree_root is not None
        else default_worktree_root(repo_root)
    )
    list_result = runner(["git", "worktree", "list", "--porcelain"], repo_root)
    if list_result.returncode != 0:
        stderr = list_result.stderr.strip() or "git worktree list failed"
        raise ValueError(stderr)

    root_with_sep = f"{resolved_worktree_root}{Path('/')}"
    worktrees: list[dict[str, Any]] = []
    for record in parse_worktree_list_output(list_result.stdout):
        path_value = record.get("worktree")
        if not path_value:
            continue

        path = Path(path_value).expanduser().resolve()
        path_text = str(path)
        if path != resolved_worktree_root and not path_text.startswith(root_with_sep):
            continue

        branch_name = record.get("branch")
        branch_name = branch_name.removeprefix("refs/heads/") if branch_name else None
        if not is_managed_branch_name(branch_name):
            continue

        worktrees.append(
            {
                "path": path_text,
                "branch_name": branch_name,
                "head": record.get("HEAD"),
                "locked": "locked" in record,
                "prunable": "prunable" in record,
            }
        )

    worktrees.sort(key=lambda item: (item["branch_name"], item["path"]))
    return {
        "repo_root": repo_root,
        "worktree_root": resolved_worktree_root,
        "worktrees": worktrees,
    }


def cleanup_investigations(
    *,
    target_repo_path: str | Path,
    worktree_root: str | Path | None = None,
    remove_branches: bool = False,
    dry_run: bool = False,
    runner: CommandRunner = run_command,
) -> dict[str, Any]:
    listed = list_managed_worktrees(
        target_repo_path=target_repo_path,
        worktree_root=worktree_root,
        runner=runner,
    )
    listed_branches = list_managed_branches(
        target_repo_path=target_repo_path,
        runner=runner,
    )
    repo_root = listed["repo_root"]
    resolved_worktree_root = listed["worktree_root"]
    active_worktrees = {
        worktree["branch_name"]: {**worktree, "has_worktree": True, "orphan_branch": False}
        for worktree in listed["worktrees"]
    }
    worktrees = [
        _managed_worktree_record_for_branch(branch_name, active_worktrees)
        for branch_name in listed_branches["branches"]
    ]

    results: list[dict[str, Any]] = []
    removed_count = 0
    failed_count = 0

    for worktree in worktrees:
        path = worktree["path"]
        branch_name = worktree["branch_name"]
        result = dict(worktree)
        if path:
            result["remove_worktree_command"] = ["git", "worktree", "remove", path, "--force"]
        if remove_branches and branch_name:
            result["remove_branch_command"] = ["git", "branch", "-D", branch_name]

        if dry_run:
            result["status"] = "planned_remove"
            results.append(result)
            continue

        if path:
            remove_worktree_result = runner(result["remove_worktree_command"], repo_root)
            if remove_worktree_result.returncode != 0:
                result["status"] = "worktree_remove_failed"
                result["error"] = (
                    remove_worktree_result.stderr.strip() or "git worktree remove failed"
                )
                result["worktree_stdout"] = _truncate_output(remove_worktree_result.stdout)
                result["worktree_stderr"] = _truncate_output(remove_worktree_result.stderr)
                results.append(result)
                failed_count += 1
                continue

        if remove_branches and branch_name:
            remove_branch_result = runner(result["remove_branch_command"], repo_root)
            if remove_branch_result.returncode != 0:
                result["status"] = "branch_remove_failed"
                result["error"] = (
                    remove_branch_result.stderr.strip() or "git branch -D failed"
                )
                result["branch_stdout"] = _truncate_output(remove_branch_result.stdout)
                result["branch_stderr"] = _truncate_output(remove_branch_result.stderr)
                results.append(result)
                failed_count += 1
                continue

            result["status"] = "removed"
        results.append(result)
        removed_count += 1

    return {
        "summary": {
            "target_repo_path": str(repo_root),
            "worktree_root": str(resolved_worktree_root),
            "matched_count": len(worktrees),
            "removed_count": removed_count,
            "planned_count": sum(1 for result in results if result["status"] == "planned_remove"),
            "failed_count": failed_count,
            "remove_branches": remove_branches,
            "dry_run": dry_run,
        },
        "worktrees": results,
    }


def _is_existing_managed_branch_error(stderr: str, branch_name: str) -> bool:
    return (
        is_managed_branch_name(branch_name)
        and f"a branch named '{branch_name}' already exists" in stderr
    )


def _cleanup_stale_managed_branch(
    *,
    repo_root: Path,
    worktree_path: Path,
    branch_name: str,
    runner: CommandRunner,
) -> dict[str, Any] | None:
    path_text = str(worktree_path)
    path_cleanup_performed = worktree_path.exists()
    remove_path_result = None
    if worktree_path.exists():
        remove_path_result = runner(
            ["git", "worktree", "remove", path_text, "--force"],
            repo_root,
        )
        if remove_path_result.returncode != 0:
            return {
                "status": "stale_cleanup_failed",
                "error": remove_path_result.stderr.strip() or "git worktree remove failed",
                "cleanup_command": ["git", "worktree", "remove", path_text, "--force"],
                "cleanup_stdout": _truncate_output(remove_path_result.stdout),
                "cleanup_stderr": _truncate_output(remove_path_result.stderr),
            }

    remove_branch_result = runner(["git", "branch", "-D", branch_name], repo_root)
    if remove_branch_result.returncode != 0:
        return {
            "status": "stale_cleanup_failed",
            "error": remove_branch_result.stderr.strip() or "git branch -D failed",
            "cleanup_command": ["git", "branch", "-D", branch_name],
            "cleanup_stdout": _truncate_output(remove_branch_result.stdout),
            "cleanup_stderr": _truncate_output(remove_branch_result.stderr),
        }

    return {
        "status": "stale_cleanup_removed",
        "path_cleanup_performed": path_cleanup_performed,
        "cleanup_commands": [
            *(
                [["git", "worktree", "remove", path_text, "--force"]]
                if remove_path_result is not None
                else []
            ),
            ["git", "branch", "-D", branch_name],
        ],
        "cleanup_stdout": _truncate_output(remove_branch_result.stdout),
        "cleanup_stderr": _truncate_output(remove_branch_result.stderr),
    }


def _investigate_one(
    target: InvestigationTarget,
    *,
    repo_root: Path,
    worktree_root: Path,
    agent: str,
    opencode_bin: str,
    opencode_mode: str,
    opencode_attach_url: str | None,
    dry_run: bool,
    runner: CommandRunner,
) -> dict[str, Any]:
    report_filename = safe_report_filename(target.task_name)
    branch_name = build_branch_name(target)
    worktree_path = build_worktree_path(worktree_root, target)
    base_ref = target.revision or "HEAD"
    prompt = build_investigation_prompt(target, report_filename)
    worktree_command = [
        "git",
        "worktree",
        "add",
        "-b",
        branch_name,
        str(worktree_path),
        base_ref,
    ]
    opencode_modes = _resolve_opencode_modes(
        opencode_mode=opencode_mode,
        opencode_attach_url=opencode_attach_url,
    )
    opencode_command = build_opencode_command(
        opencode_bin=opencode_bin,
        worktree_path=worktree_path,
        agent=agent,
        prompt=prompt,
        opencode_mode=opencode_modes[0],
        opencode_attach_url=opencode_attach_url,
    )

    result: dict[str, Any] = {
        "variant": target.variant,
        "task_name": target.task_name,
        "task_url": target.task_url,
        "revision": target.revision,
        "branch": target.branch,
        "base_ref": base_ref,
        "worktree_path": str(worktree_path),
        "branch_name": branch_name,
        "report_filename": report_filename,
        "worktree_command": worktree_command,
        "opencode_mode": opencode_modes[0],
        "opencode_command": opencode_command,
        "opencode_attempts": [],
        "worktree_reused": False,
    }

    if worktree_path.exists():
        result["worktree_reused"] = True
        result["worktree_already_exists"] = True
        markdown_files, scan_error = find_untracked_markdown_files(worktree_path, runner)
        if scan_error is not None:
            result["existing_worktree_scan_error"] = (
                scan_error.stderr.strip() or "git status failed for existing worktree"
            )
            result["existing_worktree_scan_stdout"] = _truncate_output(scan_error.stdout)
            result["existing_worktree_scan_stderr"] = _truncate_output(scan_error.stderr)
        if markdown_files:
            result["status"] = "already_completed"
            result["existing_report_files"] = markdown_files
            return result

    if dry_run:
        result["status"] = "planned"
        return result

    stale_cleanup = None
    if not worktree_path.exists():
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        worktree_result = runner(worktree_command, repo_root)
        if worktree_result.returncode != 0:
            if _is_existing_managed_branch_error(worktree_result.stderr, branch_name):
                stale_cleanup = _cleanup_stale_managed_branch(
                    repo_root=repo_root,
                    worktree_path=worktree_path,
                    branch_name=branch_name,
                    runner=runner,
                )
                if (
                    stale_cleanup is not None
                    and stale_cleanup["status"] == "stale_cleanup_removed"
                ):
                    worktree_result = runner(worktree_command, repo_root)

            if worktree_result.returncode != 0:
                if stale_cleanup is not None:
                    result["stale_cleanup"] = stale_cleanup
                result["status"] = "worktree_failed"
                result["error"] = worktree_result.stderr.strip() or "git worktree add failed"
                result["worktree_stdout"] = _truncate_output(worktree_result.stdout)
                result["worktree_stderr"] = _truncate_output(worktree_result.stderr)
                return result

        if stale_cleanup is not None:
            result["stale_cleanup"] = stale_cleanup

    for attempt_index, attempted_mode in enumerate(opencode_modes, start=1):
        current_command = build_opencode_command(
            opencode_bin=opencode_bin,
            worktree_path=worktree_path,
            agent=agent,
            prompt=prompt,
            opencode_mode=attempted_mode,
            opencode_attach_url=opencode_attach_url,
        )
        attempt_result = runner(current_command, worktree_path)
        attempt_summary = {
            "attempt": attempt_index,
            "mode": attempted_mode,
            "command": current_command,
            "returncode": attempt_result.returncode,
            "stdout": _truncate_output(attempt_result.stdout),
            "stderr": _truncate_output(attempt_result.stderr),
        }
        result["opencode_attempts"].append(attempt_summary)

        if attempt_result.returncode == 0:
            result["status"] = "launched"
            result["opencode_mode"] = attempted_mode
            result["opencode_command"] = current_command
            result["opencode_stdout"] = attempt_summary["stdout"]
            result["opencode_stderr"] = attempt_summary["stderr"]
            result["fallback_used"] = attempt_index > 1
            return result

        status, error = describe_opencode_failure(
            attempt_result,
            attempted_mode=attempted_mode,
        )
        can_retry = (
            status == "session_create_failed"
            and attempt_index < len(opencode_modes)
        )
        if can_retry:
            continue

        result["status"] = status
        result["error"] = error
        result["opencode_mode"] = attempted_mode
        result["opencode_command"] = current_command
        result["opencode_stdout"] = attempt_summary["stdout"]
        result["opencode_stderr"] = attempt_summary["stderr"]
        result["fallback_used"] = attempt_index > 1
        return result

    result["status"] = "session_create_failed"
    result["error"] = "opencode could not create a session"
    result["fallback_used"] = len(opencode_modes) > 1
    return result


def run_investigations(
    targets: Sequence[InvestigationTarget],
    *,
    target_repo_path: str | Path,
    worktree_root: str | Path | None = None,
    agent: str = "nds-e2e-investigator",
    opencode_bin: str = "opencode",
    opencode_mode: str = "auto",
    opencode_attach_url: str | None = None,
    jobs: int = 1,
    dry_run: bool = False,
    runner: CommandRunner = run_command,
) -> dict[str, Any]:
    if jobs < 1:
        raise ValueError("jobs must be >= 1")
    _resolve_opencode_modes(
        opencode_mode=opencode_mode,
        opencode_attach_url=opencode_attach_url,
    )

    repo_root = resolve_repo_root(target_repo_path, runner)
    resolved_worktree_root = (
        Path(worktree_root).expanduser().resolve()
        if worktree_root is not None
        else default_worktree_root(repo_root)
    )

    indexed_targets = list(enumerate(targets))
    ordered_results: list[dict[str, Any] | None] = [None] * len(indexed_targets)

    with ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = {
            executor.submit(
                _investigate_one,
                target,
                repo_root=repo_root,
                worktree_root=resolved_worktree_root,
                agent=agent,
                opencode_bin=opencode_bin,
                opencode_mode=opencode_mode,
                opencode_attach_url=opencode_attach_url,
                dry_run=dry_run,
                runner=runner,
            ): index
            for index, target in indexed_targets
        }
        for future in as_completed(futures):
            index = futures[future]
            ordered_results[index] = future.result()

    investigations = [result for result in ordered_results if result is not None]
    launched_count = sum(1 for result in investigations if result["status"] == "launched")
    planned_count = sum(1 for result in investigations if result["status"] == "planned")
    already_completed_count = sum(
        1 for result in investigations if result["status"] == "already_completed"
    )
    reused_worktree_count = sum(
        1 for result in investigations if result.get("worktree_reused")
    )

    return {
        "summary": {
            "target_repo_path": str(repo_root),
            "worktree_root": str(resolved_worktree_root),
            "requested_streak_count": len(targets),
            "launched_count": launched_count,
            "planned_count": planned_count,
            "already_completed_count": already_completed_count,
            "reused_worktree_count": reused_worktree_count,
            "failed_to_launch_count": len(targets)
            - launched_count
            - planned_count
            - already_completed_count,
            "jobs": jobs,
            "opencode_mode": opencode_mode,
            "opencode_attach_url": opencode_attach_url,
            "dry_run": dry_run,
        },
        "investigations": investigations,
    }
