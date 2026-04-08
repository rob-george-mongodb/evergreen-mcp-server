import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evergreen_waterfall_triage import investigation_cli
from evergreen_waterfall_triage.investigation import CommandResult


def test_main_reads_triage_json_and_emits_summary(tmp_path, capsys):
    triage_json = tmp_path / "qaFailures.json"
    triage_json.write_text(
        json.dumps(
            {
                "streaks": [
                    {
                        "variant": "ACWorkloadManagement",
                        "task_name": "E2E_NDS_ReplicaSets",
                        "latest_failure": {
                            "task_url": "https://evergreen.mongodb.com/task/abc123",
                            "revision": "deadbeefcafebabe",
                        },
                    }
                ]
            }
        )
    )
    repo_root = tmp_path / "mms"
    repo_root.mkdir()

    def fake_runner(command, cwd=None):
        if list(command[:3]) == ["git", "rev-parse", "--show-toplevel"]:
            return CommandResult(0, f"{repo_root}\n", "")
        return CommandResult(0, "ok", "")

    exit_code = investigation_cli.main(
        [
            "launch",
            "--triageJson",
            str(triage_json),
            "--targetRepoPath",
            str(repo_root),
            "--dryRun",
        ],
        command_runner=fake_runner,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["summary"]["planned_count"] == 1
    assert payload["investigations"][0]["status"] == "planned"


def test_main_uses_live_query_runner_when_triage_json_not_provided(tmp_path, capsys):
    repo_root = tmp_path / "mms"
    repo_root.mkdir()
    captured_requests = []

    def fake_triage_runner(request):
        captured_requests.append(request)
        return {
            "streaks": [
                {
                    "variant": "ACWorkloadManagement",
                    "task_name": "E2E_NDS_ReplicaSets",
                    "latest_failure": {
                        "task_url": "https://evergreen.mongodb.com/task/abc123",
                    },
                }
            ]
        }

    def fake_runner(command, cwd=None):
        if list(command[:3]) == ["git", "rev-parse", "--show-toplevel"]:
            return CommandResult(0, f"{repo_root}\n", "")
        return CommandResult(0, "ok", "")

    exit_code = investigation_cli.main(
        [
            "launch",
            "--projectIdentifier",
            "mms-v20260506",
            "--variants",
            "ACWorkloadManagement,Backup",
            "--targetRepoPath",
            str(repo_root),
            "--dryRun",
        ],
        triage_runner=fake_triage_runner,
        command_runner=fake_runner,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert captured_requests[0].project_identifier == "mms-v20260506"
    assert captured_requests[0].variants == ["ACWorkloadManagement", "Backup"]


def test_launch_parses_opencode_mode_and_attach_url(tmp_path, capsys):
    triage_json = tmp_path / "qaFailures.json"
    triage_json.write_text(
        json.dumps(
            {
                "streaks": [
                    {
                        "variant": "ACWorkloadManagement",
                        "task_name": "E2E_NDS_ReplicaSets",
                        "latest_failure": {
                            "task_url": "https://evergreen.mongodb.com/task/abc123",
                        },
                    }
                ]
            }
        )
    )
    repo_root = tmp_path / "mms"
    repo_root.mkdir()

    def fake_runner(command, cwd=None):
        if list(command[:3]) == ["git", "rev-parse", "--show-toplevel"]:
            return CommandResult(0, f"{repo_root}\n", "")
        return CommandResult(0, "ok", "")

    exit_code = investigation_cli.main(
        [
            "launch",
            "--triageJson",
            str(triage_json),
            "--targetRepoPath",
            str(repo_root),
            "--opencodeMode",
            "attach",
            "--opencodeAttachUrl",
            "http://localhost:4096",
            "--dryRun",
        ],
        command_runner=fake_runner,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["summary"]["opencode_mode"] == "attach"
    assert payload["summary"]["opencode_attach_url"] == "http://localhost:4096"


def test_validation_rejects_mixed_input_modes(tmp_path, capsys):
    repo_root = tmp_path / "mms"
    repo_root.mkdir()

    exit_code = investigation_cli.main(
        [
            "launch",
            "--triageJson",
            "-",
            "--projectIdentifier",
            "mms",
            "--targetRepoPath",
            str(repo_root),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert captured.out == ""
    assert "either --triageJson or live query arguments" in captured.err


def test_validation_requires_project_identifier_without_triage_json(tmp_path, capsys):
    repo_root = tmp_path / "mms"
    repo_root.mkdir()

    exit_code = investigation_cli.main(
        [
            "launch",
            "--variant",
            "ACWorkloadManagement",
            "--targetRepoPath",
            str(repo_root),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert captured.out == ""
    assert "--projectIdentifier is required" in captured.err


def test_cleanup_subcommand_emits_planned_removals(tmp_path, capsys):
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

    exit_code = investigation_cli.main(
        [
            "cleanup",
            "--targetRepoPath",
            str(repo_root),
            "--worktreeRoot",
            str(worktree_root),
            "--removeBranches",
            "--dryRun",
        ],
        command_runner=fake_runner,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["summary"]["planned_count"] == 1
    assert payload["worktrees"][0]["status"] == "planned_remove"
