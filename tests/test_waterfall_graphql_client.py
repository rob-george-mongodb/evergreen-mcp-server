"""Tests for EvergreenGraphQLClient.get_waterfall_failed_tasks merging logic."""

import unittest
from unittest.mock import AsyncMock, patch

from evergreen_mcp.evergreen_graphql_client import EvergreenGraphQLClient


class TestGetWaterfallFailedTasks(unittest.IsolatedAsyncioTestCase):
    """Test the waterfall task merging/filtering logic in the graphql client."""

    def _make_client(self):
        """Create a client without real network connections."""
        client = object.__new__(EvergreenGraphQLClient)
        return client

    async def test_empty_variants_raises(self):
        client = self._make_client()
        with self.assertRaises(ValueError, msg="At least one variant must be provided"):
            await client.get_waterfall_failed_tasks("mms", [])

    async def test_returns_most_recent_version(self):
        """Most recent version by startTime should be selected."""
        client = self._make_client()

        query_results = {
            "waterfall": {
                "flattenedVersions": [
                    {
                        "id": "v-old",
                        "revision": "aaa",
                        "branch": "main",
                        "startTime": "2025-01-01T10:00:00Z",
                        "finishTime": "2025-01-01T11:00:00Z",
                        "tasks": {
                            "data": [
                                {
                                    "id": "t-old",
                                    "displayName": "compile",
                                    "status": "failed",
                                }
                            ]
                        },
                    },
                    {
                        "id": "v-new",
                        "revision": "bbb",
                        "branch": "main",
                        "startTime": "2025-01-02T10:00:00Z",
                        "finishTime": "2025-01-02T11:00:00Z",
                        "tasks": {
                            "data": [
                                {
                                    "id": "t-new",
                                    "displayName": "test",
                                    "status": "failed",
                                }
                            ]
                        },
                    },
                ]
            }
        }

        with patch.object(
            client, "_execute_query", new=AsyncMock(return_value=query_results)
        ):
            result = await client.get_waterfall_failed_tasks("mms", ["linux"])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "v-new")
        self.assertEqual(len(result[0]["tasks"]), 1)
        self.assertEqual(result[0]["tasks"][0]["id"], "t-new")

    async def test_skips_versions_without_start_time(self):
        """Versions without startTime should be excluded."""
        client = self._make_client()

        query_results = {
            "waterfall": {
                "flattenedVersions": [
                    {
                        "id": "v-no-start",
                        "revision": "aaa",
                        "branch": "main",
                        "startTime": None,
                        "finishTime": "2025-01-01T11:00:00Z",
                        "tasks": {
                            "data": [
                                {
                                    "id": "t1",
                                    "displayName": "compile",
                                    "status": "failed",
                                }
                            ]
                        },
                    },
                    {
                        "id": "v-no-tasks",
                        "revision": "bbb",
                        "branch": "main",
                        "startTime": "2025-01-02T10:00:00Z",
                        "finishTime": "2025-01-02T11:00:00Z",
                        "tasks": {"data": []},
                    },
                ]
            }
        }

        with patch.object(
            client, "_execute_query", new=AsyncMock(return_value=query_results)
        ):
            result = await client.get_waterfall_failed_tasks("mms", ["linux"])

        self.assertEqual(result, [])

    async def test_merges_tasks_across_variants(self):
        """Tasks from multiple variants for the same version are merged without duplication."""
        client = self._make_client()

        # Different results per variant
        def make_query_result(task_id, task_name):
            return {
                "waterfall": {
                    "flattenedVersions": [
                        {
                            "id": "v-shared",
                            "revision": "abc",
                            "branch": "main",
                            "startTime": "2025-01-01T10:00:00Z",
                            "finishTime": "2025-01-01T11:00:00Z",
                            "tasks": {
                                "data": [
                                    {
                                        "id": task_id,
                                        "displayName": task_name,
                                        "status": "failed",
                                    }
                                ]
                            },
                        }
                    ]
                }
            }

        call_count = 0

        async def mock_execute(query, variables):
            nonlocal call_count
            call_count += 1
            variant = variables["tasksOptions"]["variant"]
            if variant == "linux":
                return make_query_result("t-linux", "linux-compile")
            elif variant == "windows":
                return make_query_result("t-windows", "windows-compile")
            return {"waterfall": {"flattenedVersions": []}}

        with patch.object(
            client, "_execute_query", new=AsyncMock(side_effect=mock_execute)
        ):
            result = await client.get_waterfall_failed_tasks(
                "mms", ["linux", "windows"]
            )

        self.assertEqual(call_count, 2)
        self.assertEqual(len(result), 1)
        version = result[0]
        self.assertEqual(version["id"], "v-shared")
        task_ids = {t["id"] for t in version["tasks"]}
        self.assertIn("t-linux", task_ids)
        self.assertIn("t-windows", task_ids)
        self.assertIn("linux", version["variants"])
        self.assertIn("windows", version["variants"])

    async def test_deduplicates_tasks_from_same_variant(self):
        """Duplicate task IDs within a version are not added twice."""
        client = self._make_client()

        query_results = {
            "waterfall": {
                "flattenedVersions": [
                    {
                        "id": "v1",
                        "revision": "abc",
                        "branch": "main",
                        "startTime": "2025-01-01T10:00:00Z",
                        "finishTime": "2025-01-01T11:00:00Z",
                        "tasks": {
                            "data": [
                                {
                                    "id": "t1",
                                    "displayName": "compile",
                                    "status": "failed",
                                },
                                {
                                    "id": "t1",
                                    "displayName": "compile",
                                    "status": "failed",
                                },  # duplicate
                            ]
                        },
                    }
                ]
            }
        }

        with patch.object(
            client, "_execute_query", new=AsyncMock(return_value=query_results)
        ):
            result = await client.get_waterfall_failed_tasks("mms", ["linux"])

        self.assertEqual(len(result[0]["tasks"]), 1)

    async def test_returns_empty_when_no_failing_versions(self):
        client = self._make_client()

        query_results = {"waterfall": {"flattenedVersions": []}}
        with patch.object(
            client, "_execute_query", new=AsyncMock(return_value=query_results)
        ):
            result = await client.get_waterfall_failed_tasks("mms", ["linux"])

        self.assertEqual(result, [])

    async def test_skips_versions_without_finish_time(self):
        """Versions with startTime but no finishTime should be excluded (M1)."""
        client = self._make_client()

        query_results = {
            "waterfall": {
                "flattenedVersions": [
                    {
                        "id": "v-in-flight",
                        "revision": "aaa",
                        "branch": "main",
                        "startTime": "2025-01-01T10:00:00Z",
                        "finishTime": None,
                        "tasks": {
                            "data": [
                                {
                                    "id": "t1",
                                    "displayName": "compile",
                                    "status": "failed",
                                }
                            ]
                        },
                    },
                    {
                        "id": "v-finished",
                        "revision": "bbb",
                        "branch": "main",
                        "startTime": "2025-01-02T10:00:00Z",
                        "finishTime": "2025-01-02T11:00:00Z",
                        "tasks": {
                            "data": [
                                {"id": "t2", "displayName": "test", "status": "failed"}
                            ]
                        },
                    },
                ]
            }
        }

        with patch.object(
            client, "_execute_query", new=AsyncMock(return_value=query_results)
        ):
            result = await client.get_waterfall_failed_tasks("mms", ["linux"])

        # The in-flight version (no finishTime) should be excluded
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "v-finished")

    async def test_returns_empty_when_all_versions_lack_finish_time(self):
        """If every version lacks finishTime, result should be empty."""
        client = self._make_client()

        query_results = {
            "waterfall": {
                "flattenedVersions": [
                    {
                        "id": "v1",
                        "revision": "aaa",
                        "branch": "main",
                        "startTime": "2025-01-01T10:00:00Z",
                        "finishTime": None,
                        "tasks": {
                            "data": [
                                {
                                    "id": "t1",
                                    "displayName": "compile",
                                    "status": "failed",
                                }
                            ]
                        },
                    },
                ]
            }
        }

        with patch.object(
            client, "_execute_query", new=AsyncMock(return_value=query_results)
        ):
            result = await client.get_waterfall_failed_tasks("mms", ["linux"])

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
