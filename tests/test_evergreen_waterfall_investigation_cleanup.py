import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evergreen_waterfall_triage.investigation import (
    CommandResult,
    cleanup_investigations,
    list_managed_branches,
    list_managed_worktrees,
    parse_worktree_list_output,
)


def test_parse_worktree_list_output_handles_porcelain_blocks():
    output = (
        "worktree /tmp/mms\n"
        "HEAD deadbeef\n"
        "branch refs/heads/main\n\n"
        "worktree /tmp/mms-investigations/ac/task\n"
        "HEAD cafebabe\n"
        "branch refs/heads/ai/evergreen/ac/task\n\n"
    )

    records = parse_worktree_list_output(output)

    assert len(records) == 2
    assert records[1]["branch"] == "refs/heads/ai/evergreen/ac/task"


def test_list_managed_worktrees_filters_to_managed_root(tmp_path):
    repo_root = tmp_path / "mms"
    repo_root.mkdir()
    worktree_root = tmp_path / "mms-investigations"

    def fake_runner(command, cwd=None):
        if list(command[:3]) == ["git", "rev-parse", "--show-toplevel"]:
            return CommandResult(0, f"{repo_root}\n", "")
        if list(command[:4]) == ["git", "worktree", "list", "--porcelain"]:
            return CommandResult(
                0,
                (
                    f"worktree {repo_root}\n"
                    "HEAD deadbeef\n"
                    "branch refs/heads/main\n\n"
                    f"worktree {worktree_root / 'ACPlat1' / 'task-a'}\n"
                    "HEAD cafebabe\n"
                    "branch refs/heads/ai/evergreen/acplat1/task-a\n\n"
                    f"worktree {tmp_path / 'other-root' / 'task-b'}\n"
                    "HEAD cafebabe\n"
                    "branch refs/heads/ai/evergreen/acplat1/task-b\n\n"
                ),
                "",
            )
        raise AssertionError(f"Unexpected command: {command}")

    result = list_managed_worktrees(
        target_repo_path=repo_root,
        worktree_root=worktree_root,
        runner=fake_runner,
    )

    assert len(result["worktrees"]) == 1
    assert result["worktrees"][0]["branch_name"] == "ai/evergreen/acplat1/task-a"


def test_cleanup_investigations_dry_run_reports_planned_remove(tmp_path):
    repo_root = tmp_path / "mms"
    repo_root.mkdir()
    worktree_root = tmp_path / "mms-investigations"

    def fake_runner(command, cwd=None):
        if list(command[:3]) == ["git", "rev-parse", "--show-toplevel"]:
            return CommandResult(0, f"{repo_root}\n", "")
        if list(command[:4]) == ["git", "worktree", "list", "--porcelain"]:
            return CommandResult(
                0,
                (
                    f"worktree {worktree_root / 'ACPlat1' / 'task-a'}\n"
                    "HEAD cafebabe\n"
                    "branch refs/heads/ai/evergreen/acplat1/task-a\n\n"
                ),
                "",
            )
        if list(command[:3]) == ["git", "for-each-ref", "--format=%(refname:short)"]:
            return CommandResult(0, "ai/evergreen/acplat1/task-a\n", "")
        raise AssertionError(f"Unexpected command: {command}")

    result = cleanup_investigations(
        target_repo_path=repo_root,
        worktree_root=worktree_root,
        remove_branches=True,
        dry_run=True,
        runner=fake_runner,
    )

    assert result["summary"]["planned_count"] == 1
    assert result["worktrees"][0]["status"] == "planned_remove"
    assert result["worktrees"][0]["remove_branch_command"] == [
        "git",
        "branch",
        "-D",
        "ai/evergreen/acplat1/task-a",
    ]


def test_cleanup_investigations_removes_worktree_and_branch(tmp_path):
    repo_root = tmp_path / "mms"
    repo_root.mkdir()
    worktree_root = tmp_path / "mms-investigations"
    command_calls = []

    def fake_runner(command, cwd=None):
        command_calls.append((list(command), cwd))
        if list(command[:3]) == ["git", "rev-parse", "--show-toplevel"]:
            return CommandResult(0, f"{repo_root}\n", "")
        if list(command[:4]) == ["git", "worktree", "list", "--porcelain"]:
            return CommandResult(
                0,
                (
                    f"worktree {worktree_root / 'ACPlat1' / 'task-a'}\n"
                    "HEAD cafebabe\n"
                    "branch refs/heads/ai/evergreen/acplat1/task-a\n\n"
                ),
                "",
            )
        if list(command[:3]) == ["git", "for-each-ref", "--format=%(refname:short)"]:
            return CommandResult(0, "ai/evergreen/acplat1/task-a\n", "")
        return CommandResult(0, "ok", "")

    result = cleanup_investigations(
        target_repo_path=repo_root,
        worktree_root=worktree_root,
        remove_branches=True,
        runner=fake_runner,
    )

    assert result["summary"]["removed_count"] == 1
    assert result["worktrees"][0]["status"] == "removed"
    assert command_calls[4][0][:3] == ["git", "worktree", "remove"]
    assert command_calls[5][0] == ["git", "branch", "-D", "ai/evergreen/acplat1/task-a"]


def test_list_managed_branches_returns_orphaned_managed_branches(tmp_path):
    repo_root = tmp_path / "mms"
    repo_root.mkdir()

    def fake_runner(command, cwd=None):
        if list(command[:3]) == ["git", "rev-parse", "--show-toplevel"]:
            return CommandResult(0, f"{repo_root}\n", "")
        if list(command[:3]) == ["git", "for-each-ref", "--format=%(refname:short)"]:
            return CommandResult(
                0,
                "ai/evergreen/acplat1/task-a\nai/evergreen/acplat1/task-b\nmain\n",
                "",
            )
        raise AssertionError(f"Unexpected command: {command}")

    result = list_managed_branches(target_repo_path=repo_root, runner=fake_runner)

    assert result["branches"] == [
        "ai/evergreen/acplat1/task-a",
        "ai/evergreen/acplat1/task-b",
    ]


def test_cleanup_investigations_removes_orphan_branch_without_worktree(tmp_path):
    repo_root = tmp_path / "mms"
    repo_root.mkdir()
    worktree_root = tmp_path / "mms-investigations"
    command_calls = []

    def fake_runner(command, cwd=None):
        command_list = list(command)
        command_calls.append((command_list, cwd))
        if command_list[:3] == ["git", "rev-parse", "--show-toplevel"]:
            return CommandResult(0, f"{repo_root}\n", "")
        if command_list[:4] == ["git", "worktree", "list", "--porcelain"]:
            return CommandResult(0, "", "")
        if command_list[:3] == ["git", "for-each-ref", "--format=%(refname:short)"]:
            return CommandResult(0, "ai/evergreen/acplat1/task-a\n", "")
        if command_list[:3] == ["git", "branch", "-D"]:
            return CommandResult(0, "Deleted branch ai/evergreen/acplat1/task-a\n", "")
        raise AssertionError(f"Unexpected command: {command}")

    result = cleanup_investigations(
        target_repo_path=repo_root,
        worktree_root=worktree_root,
        remove_branches=True,
        runner=fake_runner,
    )

    assert result["summary"]["removed_count"] == 1
    assert result["worktrees"][0]["orphan_branch"] is True
    assert result["worktrees"][0]["path"] is None
    assert result["worktrees"][0]["status"] == "removed"
    assert command_calls[4][0] == ["git", "branch", "-D", "ai/evergreen/acplat1/task-a"]
