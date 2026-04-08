import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evergreen_waterfall_triage.analysis import analyze_current_streaks, build_triage_output
from evergreen_waterfall_triage.models import TaskOccurrence, VariantHistory, WaterfallVersion


def _task(variant: str, version_id: str, task_name: str, status: str) -> TaskOccurrence:
    return TaskOccurrence(
        variant=variant,
        task_name=task_name,
        task_id=f"{version_id}-{task_name}",
        status=status,
        version_id=version_id,
        revision=f"rev-{version_id}",
        start_time=f"2026-04-{version_id[-2:]}T10:00:00Z",
        finish_time=f"2026-04-{version_id[-2:]}T11:00:00Z",
    )


def _version(project: str, variant: str, version_id: str, *tasks: TaskOccurrence) -> WaterfallVersion:
    return WaterfallVersion(
        project_identifier=project,
        variant=variant,
        version_id=version_id,
        revision=f"rev-{version_id}",
        branch="main",
        start_time=f"2026-04-{version_id[-2:]}T10:00:00Z",
        finish_time=f"2026-04-{version_id[-2:]}T11:00:00Z",
        tasks=tasks,
    )


def _history(project: str, variant: str, *versions: WaterfallVersion) -> VariantHistory:
    return VariantHistory(
        project_identifier=project,
        variant=variant,
        waterfall_limit=200,
        queried_statuses=(),
        fetched_version_count=len(versions),
        versions=versions,
    )


def test_success_resets_and_only_failed_counts():
    history = _history(
        "mms",
        "linux",
        _version("mms", "linux", "v03", _task("linux", "v03", "taskA", "failed")),
        _version("mms", "linux", "v02", _task("linux", "v02", "taskA", "started")),
        _version("mms", "linux", "v01", _task("linux", "v01", "taskA", "success")),
    )

    report = analyze_current_streaks("mms", [history])

    assert len(report.streaks) == 1
    streak = report.streaks[0]
    assert streak.failure_count == 1
    assert streak.reset_occurrence is not None
    assert streak.reset_occurrence.status == "success"
    assert streak.truncated is False


def test_neutral_status_and_absence_do_not_reset_open_streak():
    history = _history(
        "mms",
        "linux",
        _version("mms", "linux", "v05", _task("linux", "v05", "taskA", "started")),
        _version("mms", "linux", "v04", _task("linux", "v04", "taskA", "failed")),
        _version("mms", "linux", "v03"),
        _version("mms", "linux", "v02", _task("linux", "v02", "taskA", "blocked")),
        _version("mms", "linux", "v01", _task("linux", "v01", "taskA", "failed")),
    )

    report = analyze_current_streaks("mms", [history], min_num_consecutive_failures=2)

    assert len(report.streaks) == 1
    streak = report.streaks[0]
    assert streak.failure_count == 2
    assert streak.truncated is True


def test_latest_occurrence_preserves_leading_neutral_status_before_failure():
    history = _history(
        "mms",
        "linux",
        _version("mms", "linux", "v03", _task("linux", "v03", "taskA", "started")),
        _version("mms", "linux", "v02", _task("linux", "v02", "taskA", "failed")),
        _version("mms", "linux", "v01", _task("linux", "v01", "taskA", "success")),
    )

    report = analyze_current_streaks("mms", [history])

    assert len(report.streaks) == 1
    streak = report.streaks[0]
    assert streak.latest_occurrence.status == "started"
    assert streak.latest_failure.status == "failed"


def test_same_task_name_in_different_variants_produces_distinct_streaks():
    linux_history = _history(
        "mms",
        "linux",
        _version("mms", "linux", "v02", _task("linux", "v02", "taskA", "failed")),
        _version("mms", "linux", "v01", _task("linux", "v01", "taskA", "success")),
    )
    windows_history = _history(
        "mms",
        "windows",
        _version(
            "mms",
            "windows",
            "v02",
            _task("windows", "v02", "taskA", "failed"),
        ),
        _version(
            "mms",
            "windows",
            "v01",
            _task("windows", "v01", "taskA", "failed"),
        ),
    )

    report = analyze_current_streaks("mms", [linux_history, windows_history])

    assert [(streak.variant, streak.task_name) for streak in report.streaks] == [
        ("windows", "taskA"),
        ("linux", "taskA"),
    ]


def test_build_triage_output_includes_rules_links_and_task_urls():
    history = _history(
        "mms",
        "linux",
        _version("mms", "linux", "v02", _task("linux", "v02", "taskA", "failed")),
        _version("mms", "linux", "v01", _task("linux", "v01", "taskA", "success")),
    )

    output = build_triage_output("mms", [history])

    assert output["rules"]["failure_count_statuses"] == ["failed"]
    assert output["rules"]["reset_statuses"] == ["success"]
    assert output["links"]["task_url_template"].endswith("/task/{task_id}")
    assert output["streaks"][0]["latest_failure"]["task_url"].endswith("/task/v02-taskA")
