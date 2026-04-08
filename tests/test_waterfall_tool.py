#!/usr/bin/env python3
"""Tests for waterfall failed tasks tool normalization"""

import asyncio
import unittest

from evergreen_mcp.waterfall_tools import fetch_waterfall_failed_tasks


class FakeClient:
    """Simulates EvergreenGraphQLClient.get_waterfall_failed_tasks, which returns at most
    one already-selected (most recent) failing version, or an empty list."""

    async def get_waterfall_failed_tasks(
        self, project_identifier, variants, statuses, waterfall_limit
    ):
        if "linux" in variants or "windows" in variants:
            # Return the single most recent failing version (as the real client does)
            return [
                {
                    "id": "v2",
                    "revision": "def456",
                    "branch": "main",
                    "startTime": "2025-11-11T10:05:00Z",
                    "finishTime": "2025-11-11T11:00:00Z",
                    "tasks": [
                        {"id": "t2", "displayName": "test", "status": "system-failed"},
                        {"id": "t3", "displayName": "lint", "status": "failed"},
                    ],
                    "variants": sorted(list(variants)),
                },
            ]
        return []


class TestWaterfallTool(unittest.TestCase):
    def test_normalization(self):
        async def run_test():
            client = FakeClient()
            args = {
                "project_identifier": "mms",
                "variants": ["linux", "windows"],
                "waterfall_limit": 10,
            }
            result = await fetch_waterfall_failed_tasks(client, args)
            self.assertIn("versions", result)
            self.assertEqual(result["project_identifier"], "mms")
            self.assertEqual(result["summary"]["total_versions_with_failures"], 1)
            self.assertEqual(result["summary"]["total_failed_tasks"], 2)
            self.assertEqual(len(result["versions"]), 1)
            version = result["versions"][0]
            self.assertEqual(version["version_id"], "v2")
            self.assertEqual(version["revision"], "def456")
            self.assertEqual(version["failed_task_count"], 2)
            self.assertEqual(len(version["failed_tasks"]), 2)
            task_ids = {t["task_id"] for t in version["failed_tasks"]}
            self.assertIn("t2", task_ids)
            self.assertIn("t3", task_ids)
            # Variants should be propagated
            self.assertIn("linux", version["variants_with_failures"])
            self.assertIn("windows", version["variants_with_failures"])

        asyncio.run(run_test())

    def test_single_variant(self):
        async def run_test():
            client = FakeClient()
            args = {
                "project_identifier": "mms",
                "variants": ["linux"],
                "waterfall_limit": 5,
            }
            result = await fetch_waterfall_failed_tasks(client, args)
            self.assertEqual(len(result["versions"]), 1)
            self.assertEqual(result["versions"][0]["failed_task_count"], 2)

        asyncio.run(run_test())

    def test_empty(self):
        async def run_test():
            client = FakeClient()
            args = {
                "project_identifier": "mms",
                "variants": ["macos"],  # FakeClient returns empty for this variant
                "waterfall_limit": 5,
            }
            result = await fetch_waterfall_failed_tasks(client, args)
            self.assertEqual(result["summary"]["total_versions_with_failures"], 0)
            self.assertEqual(result["summary"]["total_failed_tasks"], 0)
            self.assertEqual(result["versions"], [])

        asyncio.run(run_test())

    def test_missing_project_identifier(self):
        async def run_test():
            client = FakeClient()
            with self.assertRaises(ValueError, msg="project_identifier parameter is required"):
                await fetch_waterfall_failed_tasks(client, {"variants": ["linux"]})

        asyncio.run(run_test())

    def test_missing_variants(self):
        async def run_test():
            client = FakeClient()
            with self.assertRaises(ValueError, msg="At least one variant must be provided"):
                await fetch_waterfall_failed_tasks(
                    client, {"project_identifier": "mms", "variants": []}
                )

        asyncio.run(run_test())

    def test_suggested_next_steps_on_success(self):
        """Result summary should include next steps when failures are found."""
        async def run_test():
            client = FakeClient()
            args = {
                "project_identifier": "mms",
                "variants": ["linux"],
                "waterfall_limit": 10,
            }
            result = await fetch_waterfall_failed_tasks(client, args)
            self.assertIn("suggested_next_steps", result["summary"])
            self.assertTrue(len(result["summary"]["suggested_next_steps"]) > 0)

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
