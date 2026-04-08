import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evergreen_waterfall_triage.investigation import (
    CommandResult,
    InvestigationTarget,
    build_branch_name,
    build_investigation_prompt,
    build_opencode_command,
    build_worktree_path,
    parse_triage_report,
    run_investigations,
    safe_report_filename,
)


def test_parse_triage_report_requires_latest_failure_task_url():
    try:
        parse_triage_report(
            {
                "streaks": [
                    {
                        "variant": "ACWorkloadManagement",
                        "task_name": "taskA",
                        "latest_failure": {},
                    }
                ]
            }
        )
    except ValueError as exc:
        assert "task_url" in str(exc)
    else:
        raise AssertionError("Expected ValueError when task_url is missing")


def test_build_prompt_uses_latest_task_url_and_report_filename():
    target = InvestigationTarget(
        variant="ACWorkloadManagement",
        task_name="E2E_NDS_ReplicaSets",
        task_url="https://evergreen.mongodb.com/task/abc123",
    )

    prompt = build_investigation_prompt(target, safe_report_filename(target.task_name))

    assert "https://evergreen.mongodb.com/task/abc123" in prompt
    assert "E2E_NDS_ReplicaSets.md" in prompt


def test_branch_name_and_worktree_path_are_stable_and_sanitized(tmp_path):
    target = InvestigationTarget(
        variant="AC Workload/Management",
        task_name="E2E NDS/ReplicaSets",
        task_url="https://evergreen.mongodb.com/task/abc123",
        revision="deadbeefcafebabe",
    )

    branch_name = build_branch_name(target)
    worktree_path = build_worktree_path(tmp_path, target)

    assert branch_name.startswith("ai/evergreen/ac-workload-management/")
    assert "e2e-nds-replicasets" in branch_name
    assert worktree_path.parent.name == "ac-workload-management"
    assert "e2e-nds-replicasets" in worktree_path.name


def test_build_opencode_command_in_attach_mode_includes_attach_url(tmp_path):
    command = build_opencode_command(
        opencode_bin="opencode",
        worktree_path=tmp_path,
        agent="nds-e2e-investigator",
        prompt="investigate",
        opencode_mode="attach",
        opencode_attach_url="http://localhost:4096",
    )

    assert command[:4] == ["opencode", "run", "--attach", "http://localhost:4096"]
    assert command[-3:] == ["--dir", str(tmp_path), "investigate"]


def test_run_investigations_creates_worktree_and_opencode_commands(tmp_path):
    repo_root = tmp_path / "mms"
    repo_root.mkdir()
    command_calls = []

    def fake_runner(command, cwd=None):
        command_calls.append((list(command), cwd))
        if list(command[:3]) == ["git", "rev-parse", "--show-toplevel"]:
            return CommandResult(0, f"{repo_root}\n", "")
        return CommandResult(0, "ok", "")

    targets = [
        InvestigationTarget(
            variant="ACWorkloadManagement",
            task_name="E2E_NDS_ReplicaSets",
            task_url="https://evergreen.mongodb.com/task/abc123",
            revision="deadbeefcafebabe",
        )
    ]

    result = run_investigations(
        targets,
        target_repo_path=repo_root,
        worktree_root=tmp_path / "worktrees",
        opencode_mode="local",
        jobs=2,
        runner=fake_runner,
    )

    assert result["summary"]["launched_count"] == 1
    assert result["summary"]["jobs"] == 2
    assert len(command_calls) == 3
    assert command_calls[1][0][:4] == ["git", "worktree", "add", "-b"]
    assert command_calls[2][0][:4] == ["opencode", "run", "--agent", "nds-e2e-investigator"]
    assert command_calls[2][1] == Path(result["investigations"][0]["worktree_path"])


def test_run_investigations_retries_local_after_attach_session_failure(tmp_path):
    repo_root = tmp_path / "mms"
    repo_root.mkdir()
    command_calls = []

    def fake_runner(command, cwd=None):
        command_list = list(command)
        command_calls.append((command_list, cwd))
        if command_list[:3] == ["git", "rev-parse", "--show-toplevel"]:
            return CommandResult(0, f"{repo_root}\n", "")
        if command_list[:4] == ["git", "worktree", "add", "-b"]:
            return CommandResult(0, "ok", "")
        if command_list[:4] == ["opencode", "run", "--attach", "http://localhost:4096"]:
            return CommandResult(1, "", "Error: Session not found\n")
        return CommandResult(0, "ok", "")

    targets = [
        InvestigationTarget(
            variant="ACWorkloadManagement",
            task_name="E2E_NDS_ReplicaSets",
            task_url="https://evergreen.mongodb.com/task/abc123",
        )
    ]

    result = run_investigations(
        targets,
        target_repo_path=repo_root,
        worktree_root=tmp_path / "worktrees",
        opencode_mode="auto",
        opencode_attach_url="http://localhost:4096",
        runner=fake_runner,
    )

    investigation = result["investigations"][0]
    assert investigation["status"] == "launched"
    assert investigation["fallback_used"] is True
    assert investigation["opencode_mode"] == "local"
    assert len(investigation["opencode_attempts"]) == 2
    assert investigation["opencode_attempts"][0]["mode"] == "attach"
    assert investigation["opencode_attempts"][1]["mode"] == "local"


def test_run_investigations_classifies_terminal_session_failure(tmp_path):
    repo_root = tmp_path / "mms"
    repo_root.mkdir()

    def fake_runner(command, cwd=None):
        command_list = list(command)
        if command_list[:3] == ["git", "rev-parse", "--show-toplevel"]:
            return CommandResult(0, f"{repo_root}\n", "")
        if command_list[:4] == ["git", "worktree", "add", "-b"]:
            return CommandResult(0, "ok", "")
        return CommandResult(1, "", "Error: Session not found\n")

    result = run_investigations(
        [
            InvestigationTarget(
                variant="ACWorkloadManagement",
                task_name="E2E_NDS_ReplicaSets",
                task_url="https://evergreen.mongodb.com/task/abc123",
            )
        ],
        target_repo_path=repo_root,
        worktree_root=tmp_path / "worktrees",
        opencode_mode="local",
        runner=fake_runner,
    )

    investigation = result["investigations"][0]
    assert investigation["status"] == "session_create_failed"
    assert "could not create" in investigation["error"]


def test_run_investigations_recovers_from_stale_managed_branch(tmp_path):
    repo_root = tmp_path / "mms"
    repo_root.mkdir()
    call_counts = {"worktree_add": 0}

    def fake_runner(command, cwd=None):
        command_list = list(command)
        if command_list[:3] == ["git", "rev-parse", "--show-toplevel"]:
            return CommandResult(0, f"{repo_root}\n", "")
        if command_list[:4] == ["git", "worktree", "add", "-b"]:
            call_counts["worktree_add"] += 1
            if call_counts["worktree_add"] == 1:
                branch_name = command_list[4]
                return CommandResult(
                    128,
                    "",
                    f"fatal: a branch named '{branch_name}' already exists\n",
                )
            return CommandResult(0, "ok", "")
        if command_list[:3] == ["git", "branch", "-D"]:
            return CommandResult(0, "Deleted branch\n", "")
        return CommandResult(0, "ok", "")

    result = run_investigations(
        [
            InvestigationTarget(
                variant="ACWorkloadManagement",
                task_name="E2E_NDS_ReplicaSets",
                task_url="https://evergreen.mongodb.com/task/abc123",
            )
        ],
        target_repo_path=repo_root,
        worktree_root=tmp_path / "worktrees",
        opencode_mode="local",
        runner=fake_runner,
    )

    investigation = result["investigations"][0]
    assert investigation["status"] == "launched"
    assert investigation["stale_cleanup"]["status"] == "stale_cleanup_removed"
    assert call_counts["worktree_add"] == 2


def test_run_investigations_marks_existing_worktree_path_as_failure(tmp_path):
    repo_root = tmp_path / "mms"
    repo_root.mkdir()
    target = InvestigationTarget(
        variant="ACWorkloadManagement",
        task_name="E2E_NDS_ReplicaSets",
        task_url="https://evergreen.mongodb.com/task/abc123",
    )
    existing_path = build_worktree_path(tmp_path / "worktrees", target)
    existing_path.mkdir(parents=True)

    def fake_runner(command, cwd=None):
        command_list = list(command)
        if command_list[:3] == ["git", "rev-parse", "--show-toplevel"]:
            return CommandResult(0, f"{repo_root}\n", "")
        if command_list[:3] == ["git", "status", "--porcelain"]:
            return CommandResult(0, "", "")
        if command_list[:2] == ["opencode", "run"]:
            return CommandResult(0, "ok", "")
        raise AssertionError(f"Unexpected command: {command}")

    result = run_investigations(
        [target],
        target_repo_path=repo_root,
        worktree_root=tmp_path / "worktrees",
        runner=fake_runner,
    )

    assert result["summary"]["launched_count"] == 1
    assert result["summary"]["reused_worktree_count"] == 1
    assert result["investigations"][0]["status"] == "launched"
    assert result["investigations"][0]["worktree_reused"] is True


def test_existing_worktree_with_untracked_markdown_is_already_completed(tmp_path):
    repo_root = tmp_path / "mms"
    repo_root.mkdir()
    target = InvestigationTarget(
        variant="ACWorkloadManagement",
        task_name="E2E_NDS_ReplicaSets",
        task_url="https://evergreen.mongodb.com/task/abc123",
    )
    existing_path = build_worktree_path(tmp_path / "worktrees", target)
    existing_path.mkdir(parents=True)

    def fake_runner(command, cwd=None):
        command_list = list(command)
        if command_list[:3] == ["git", "rev-parse", "--show-toplevel"]:
            return CommandResult(0, f"{repo_root}\n", "")
        if command_list[:3] == ["git", "status", "--porcelain"]:
            return CommandResult(0, "?? E2E_NDS_ReplicaSets.md\n", "")
        raise AssertionError("No other commands should run when markdown already exists")

    result = run_investigations(
        [target],
        target_repo_path=repo_root,
        worktree_root=tmp_path / "worktrees",
        runner=fake_runner,
    )

    assert result["summary"]["already_completed_count"] == 1
    assert result["summary"]["reused_worktree_count"] == 1
    assert result["investigations"][0]["status"] == "already_completed"
    assert result["investigations"][0]["existing_report_files"] == ["E2E_NDS_ReplicaSets.md"]
