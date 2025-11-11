#!/usr/bin/env python3
"""Tests for waterfall failed tasks tool normalization"""

import asyncio
import unittest

from evergreen_mcp.waterfall_tools import fetch_waterfall_failed_tasks


class FakeClient:
    async def get_waterfall_failed_tasks(self, project_identifier, variants, statuses, waterfall_limit):
        # Simulate two queries merging same version with different tasks
        if "linux" in variants and "windows" in variants:
            return [
                {
                    "id": "v1",
                    "revision": "abc123",
                    "branch": "main",
                    "startTime": "2025-11-11T10:00:00Z",
                    "tasks": [
                        {"id": "t1", "displayName": "compile", "status": "failed"},
                    ],
                },
                {
                    "id": "v2",
                    "revision": "def456",
                    "branch": "main",
                    "startTime": "2025-11-11T10:05:00Z",
                    "tasks": [
                        {"id": "t2", "displayName": "test", "status": "system-failed"},
                        {"id": "t3", "displayName": "lint", "status": "failed"},
                    ],
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
            # Expect single version now
            self.assertEqual(result["summary"]["total_versions_with_failures"], 1)
            self.assertEqual(len(result["versions"]), 1)
            first_version = result["versions"][0]
            self.assertIn("failed_tasks", first_version)
            first_task = first_version["failed_tasks"][0]
            self.assertIn("tool_args", first_task)
            self.assertIn("logs", first_task["tool_args"])
            self.assertIn("tests", first_task["tool_args"])

        asyncio.run(run_test())

    def test_empty(self):
        async def run_test():
            client = FakeClient()
            args = {
                "project_identifier": "mms",
                "variants": ["macos"],  # Fake variant returns empty
                "waterfall_limit": 5,
            }
            result = await fetch_waterfall_failed_tasks(client, args)
            self.assertEqual(result["summary"]["total_versions_with_failures"], 0)
            self.assertEqual(result["versions"], [])

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
