import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evergreen_waterfall_triage import cli


def test_main_emits_json_only_to_stdout(monkeypatch, capsys):
    def fake_runner(request):
        assert request.project_identifier == "mongodb-mongo-master"
        assert request.variants == ["linux"]
        assert request.waterfall_limit == 200
        assert request.min_num_consecutive_failures == 1
        return {"projectIdentifier": request.project_identifier, "variants": request.variants}

    monkeypatch.setattr(cli, "run_triage", fake_runner)

    exit_code = cli.main(["--projectIdentifier", "mongodb-mongo-master", "--variant", "linux"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "projectIdentifier": "mongodb-mongo-master",
        "variants": ["linux"],
    }


def test_combines_and_deduplicates_variants(monkeypatch, capsys):
    captured_requests = []

    def fake_runner(request):
        captured_requests.append(request)
        return {"ok": True}

    monkeypatch.setattr(cli, "run_triage", fake_runner)

    exit_code = cli.main(
        [
            "--projectIdentifier",
            "mongodb-mongo-master",
            "--variant",
            "linux",
            "--variant",
            "windows",
            "--variants",
            "windows,macos",
            "linux",
            "--waterfallLimit",
            "50",
            "--minNumConsecutiveFailures",
            "3",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert json.loads(captured.out) == {"ok": True}
    assert captured_requests == [
        cli.TriageRequest(
            project_identifier="mongodb-mongo-master",
            variants=["linux", "windows", "macos"],
            waterfall_limit=50,
            min_num_consecutive_failures=3,
        )
    ]


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--variant", "linux"], "the following arguments are required: --projectIdentifier"),
        (["--projectIdentifier", "mongodb-mongo-master"], "At least one variant must be provided"),
        (
            [
                "--projectIdentifier",
                "mongodb-mongo-master",
                "--variant",
                "linux",
                "--waterfallLimit",
                "0",
            ],
            "--waterfallLimit must be >= 1",
        ),
        (
            [
                "--projectIdentifier",
                "mongodb-mongo-master",
                "--variant",
                "linux",
                "--minNumConsecutiveFailures",
                "0",
            ],
            "--minNumConsecutiveFailures must be >= 1",
        ),
    ],
)
def test_validation_failures_return_nonzero_and_use_stderr(argv, message, capsys):
    exit_code = cli.main(argv)

    captured = capsys.readouterr()
    assert exit_code != 0
    assert captured.out == ""
    assert message in captured.err
