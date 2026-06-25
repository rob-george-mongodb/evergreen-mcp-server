"""
Integration tests that validate every GraphQL query in evergreen_queries.py
against the live Evergreen API. Catches schema regressions.

Run with: RUN_INTEGRATION_TESTS=1 pytest tests/test_graphql_live_queries.py -v
"""

import json
import os
import subprocess

import aiohttp
import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_INTEGRATION_TESTS") != "1",
        reason="Integration test - set RUN_INTEGRATION_TESTS=1 to run",
    ),
]

GRAPHQL_ENDPOINT = "https://evergreen.corp.mongodb.com/graphql/query"
TEST_PATCH_ID = "6a3c95198972470007910a4d"
TEST_PROJECT_ID = "evergreen"


@pytest.fixture(scope="session")
def bearer_token():
    """Get a valid OAuth token from the evergreen CLI."""
    result = subprocess.run(
        ["evergreen", "client", "get-oauth-token"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"evergreen CLI failed: {result.stderr}"
    token = result.stdout.strip()
    assert token, "No token returned"
    return token


@pytest.fixture(scope="session")
def user_id(bearer_token):
    """Derive the Evergreen user ID from the JWT (same logic as mcp_tools._user_from_jwt)."""
    import base64
    payload = bearer_token.split(".")[1]
    payload += "=" * (4 - len(payload) % 4)
    decoded = json.loads(base64.urlsafe_b64decode(payload))
    email = decoded.get("email", "")
    if "@" in email:
        return email.split("@")[0]
    return decoded.get("preferred_username") or decoded.get("sub") or ""


@pytest.fixture(scope="session")
async def graphql_session(bearer_token):
    """Reusable aiohttp session for GraphQL queries."""
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        yield session


async def _execute_graphql(session, query, variables=None):
    """Execute a GraphQL query and return the parsed response."""
    body = {"query": query}
    if variables:
        body["variables"] = variables
    async with session.post(GRAPHQL_ENDPOINT, json=body) as resp:
        assert resp.status == 200, f"HTTP {resp.status}"
        result = await resp.json()
        assert "errors" not in result, f"GraphQL errors: {json.dumps(result['errors'], indent=2)}"
        assert result.get("data") is not None, "Response data is null"
        return result["data"]


class TestGetProjects:
    async def test_get_projects(self, graphql_session):
        from evergreen_mcp.evergreen_queries import GET_PROJECTS
        data = await _execute_graphql(graphql_session, GET_PROJECTS)
        assert "projects" in data
        assert isinstance(data["projects"], list)
        assert len(data["projects"]) > 0
        group = data["projects"][0]
        assert "groupDisplayName" in group
        assert "projects" in group
        project = group["projects"][0]
        assert "id" in project
        assert "identifier" in project
        assert "displayName" in project


class TestGetProject:
    async def test_get_project(self, graphql_session):
        from evergreen_mcp.evergreen_queries import GET_PROJECT
        data = await _execute_graphql(
            graphql_session, GET_PROJECT,
            variables={"projectId": TEST_PROJECT_ID},
        )
        assert "project" in data
        project = data["project"]
        assert project["identifier"] == TEST_PROJECT_ID
        assert "admins" in project
        assert "banner" in project


class TestGetUserRecentPatches:
    async def test_get_user_recent_patches(self, graphql_session, user_id):
        from evergreen_mcp.evergreen_queries import GET_USER_RECENT_PATCHES
        data = await _execute_graphql(
            graphql_session, GET_USER_RECENT_PATCHES,
            variables={"userId": user_id, "limit": 2, "page": 0},
        )
        assert "user" in data
        patches = data["user"]["patches"]["patches"]
        assert isinstance(patches, list)
        if len(patches) > 0:
            patch = patches[0]
            assert "id" in patch
            assert "projectMetadata" in patch
            assert "identifier" in patch["projectMetadata"]
            assert "versionFull" in patch


class TestGetPatchFailedTasks:
    async def test_get_patch_failed_tasks(self, graphql_session):
        from evergreen_mcp.evergreen_queries import GET_PATCH_FAILED_TASKS
        data = await _execute_graphql(
            graphql_session, GET_PATCH_FAILED_TASKS,
            variables={"patchId": TEST_PATCH_ID},
        )
        assert "patch" in data
        patch = data["patch"]
        assert patch["id"] == TEST_PATCH_ID
        assert "projectMetadata" in patch
        assert "identifier" in patch["projectMetadata"]
        version = patch["versionFull"]
        assert "tasks" in version
        tasks = version["tasks"]
        assert "count" in tasks
        assert "data" in tasks
        if tasks["count"] > 0:
            task = tasks["data"][0]
            assert "id" in task
            assert "displayName" in task
            assert "buildVariant" in task
            assert "status" in task
            assert "details" in task
            assert "logs" in task


class TestGetVersionWithFailedTasks:
    async def test_get_version_with_failed_tasks(self, graphql_session):
        from evergreen_mcp.evergreen_queries import GET_VERSION_WITH_FAILED_TASKS
        data = await _execute_graphql(
            graphql_session, GET_VERSION_WITH_FAILED_TASKS,
            variables={"versionId": TEST_PATCH_ID},
        )
        assert "version" in data
        version = data["version"]
        assert "tasks" in version


class TestGetTaskLogs:
    async def test_get_task_logs(self, graphql_session):
        from evergreen_mcp.evergreen_queries import GET_TASK_LOGS
        # First get a task ID from the known patch
        from evergreen_mcp.evergreen_queries import GET_PATCH_FAILED_TASKS
        patch_data = await _execute_graphql(
            graphql_session, GET_PATCH_FAILED_TASKS,
            variables={"patchId": TEST_PATCH_ID},
        )
        tasks = patch_data["patch"]["versionFull"]["tasks"]["data"]
        assert len(tasks) > 0, "Need at least one task to test logs"
        task_id = tasks[0]["id"]
        execution = tasks[0]["execution"]

        data = await _execute_graphql(
            graphql_session, GET_TASK_LOGS,
            variables={"taskId": task_id, "execution": execution},
        )
        assert "task" in data
        task = data["task"]
        assert task["id"] == task_id
        assert "taskLogs" in task
        assert "taskLogs" in task["taskLogs"]


class TestGetTaskTestResults:
    async def test_get_task_test_results(self, graphql_session):
        from evergreen_mcp.evergreen_queries import GET_TASK_TEST_RESULTS
        # Use the same task as the logs test
        from evergreen_mcp.evergreen_queries import GET_PATCH_FAILED_TASKS
        patch_data = await _execute_graphql(
            graphql_session, GET_PATCH_FAILED_TASKS,
            variables={"patchId": TEST_PATCH_ID},
        )
        tasks = patch_data["patch"]["versionFull"]["tasks"]["data"]
        task_id = tasks[0]["id"]
        execution = tasks[0]["execution"]

        data = await _execute_graphql(
            graphql_session, GET_TASK_TEST_RESULTS,
            variables={
                "taskId": task_id,
                "execution": execution,
                "testFilterOptions": {"limit": 5, "page": 0},
            },
        )
        assert "task" in data
        task = data["task"]
        assert "tests" in task
        assert "testResults" in task["tests"]


class TestGetInferredProjectIds:
    async def test_get_inferred_project_ids(self, graphql_session, user_id):
        from evergreen_mcp.evergreen_queries import GET_INFERRED_PROJECT_IDS
        data = await _execute_graphql(
            graphql_session, GET_INFERRED_PROJECT_IDS,
            variables={"userId": user_id, "limit": 5, "page": 0},
        )
        assert "user" in data
        patches = data["user"]["patches"]["patches"]
        if len(patches) > 0:
            patch = patches[0]
            assert "projectMetadata" in patch
            assert "identifier" in patch["projectMetadata"]
