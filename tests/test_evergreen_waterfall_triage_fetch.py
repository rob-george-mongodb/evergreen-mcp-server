import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evergreen_waterfall_triage.fetch import (
    CANONICAL_TASK_STATUS_UNIVERSE,
    fetch_waterfall_history_from_client,
    normalize_variant_history,
)


class FakeClient:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def execute(self, query, variables):
        self.calls.append((query, variables))
        return self.result


def test_normalize_variant_history_filters_incomplete_versions_and_empty_tasks():
    history = normalize_variant_history(
        project_identifier="mms",
        variant="linux",
        waterfall_limit=10,
        raw_result={
            "waterfall": {
                "flattenedVersions": [
                    {"id": "v1", "startTime": None, "finishTime": "x", "tasks": {"data": [{"id": "t1", "displayName": "taskA", "status": "failed"}]}},
                    {"id": "v2", "startTime": "x", "finishTime": None, "tasks": {"data": [{"id": "t2", "displayName": "taskA", "status": "failed"}]}},
                    {"id": "v3", "startTime": "x", "finishTime": "y", "tasks": {"data": []}},
                    {"id": "v4", "revision": "abc", "branch": "main", "startTime": "2026-04-04T10:00:00Z", "finishTime": "2026-04-04T11:00:00Z", "tasks": {"data": [{"id": "t4", "displayName": "taskA", "status": "failed"}] }},
                ]
            }
        },
    )

    assert history.eligible_version_count == 1
    assert history.skipped_missing_start_time == 1
    assert history.skipped_missing_finish_time == 1
    assert history.skipped_empty_tasks == 1
    assert history.versions[0].version_id == "v4"


def test_normalize_variant_history_raises_on_truncated_task_list():
    try:
        normalize_variant_history(
            project_identifier="mms",
            variant="linux",
            waterfall_limit=10,
            raw_result={
                "waterfall": {
                    "flattenedVersions": [
                        {
                            "id": "v4",
                            "revision": "abc",
                            "branch": "main",
                            "startTime": "2026-04-04T10:00:00Z",
                            "finishTime": "2026-04-04T11:00:00Z",
                            "tasks": {
                                "count": 2,
                                "data": [
                                    {
                                        "id": "t4",
                                        "displayName": "taskA",
                                        "status": "failed",
                                    }
                                ],
                            },
                        }
                    ]
                }
            },
        )
    except ValueError as exc:
        assert "truncated by GraphQL limit" in str(exc)
    else:
        raise AssertionError("Expected ValueError for truncated task list")


def test_fetch_waterfall_history_queries_each_variant_with_full_status_universe():
    async def run_test():
        client = FakeClient(
            {
                "waterfall": {
                    "flattenedVersions": [
                        {
                            "id": "v1",
                            "revision": "abc",
                            "branch": "main",
                            "startTime": "2026-04-01T10:00:00Z",
                            "finishTime": "2026-04-01T11:00:00Z",
                            "tasks": {"data": [{"id": "t1", "displayName": "taskA", "status": "failed"}]},
                        }
                    ]
                }
            }
        )

        histories = await fetch_waterfall_history_from_client(
            client=client,
            project_identifier="mms",
            variants=["linux", "windows"],
        )

        assert [history.variant for history in histories] == ["linux", "windows"]
        assert len(client.calls) == 2
        for _, variables in client.calls:
            assert (
                tuple(variables["tasksOptions"]["statuses"])
                == CANONICAL_TASK_STATUS_UNIVERSE
            )

    asyncio.run(run_test())
