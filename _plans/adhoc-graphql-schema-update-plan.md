# Plan: Fix GraphQL Queries for Evergreen Schema Changes

## Problem Summary

The Evergreen GraphQL schema has evolved, and 5 of 11 queries in `evergreen_queries.py` now fail with `GRAPHQL_VALIDATION_FAILED` errors against the live API. The primary breaking change is the removal of the `projectIdentifier` field from the `Patch` type — it has been replaced by `projectMetadata { identifier }`. A secondary issue is that `Patch.version` now returns `VersionLite` (not a scalar), requiring subfield selections.

### Live API Test Results (2026-06-25)

| Query | Status | Error |
|-------|--------|-------|
| `GET_PROJECTS` | ✅ PASS | — |
| `GET_PROJECT` | ✅ PASS | — (unused by tools) |
| `GET_PROJECT_SETTINGS` | ⚠️ FORBIDDEN | Permission issue, not schema (unused by tools) |
| `GET_PROJECT_PATCHES` | ❌ FAIL | `Field "version" of type "VersionLite" must have a selection of subfields` (unused by tools) |
| `GET_PROJECT_BUILDS` | ⚠️ INCOMPLETE | Has TODO comment, never imported (unused by tools) |
| `GET_USER_RECENT_PATCHES` | ❌ FAIL | `Cannot query field "projectIdentifier" on type "Patch"` |
| `GET_PATCH_FAILED_TASKS` | ❌ FAIL | `Cannot query field "projectIdentifier" on type "Patch"` |
| `GET_VERSION_WITH_FAILED_TASKS` | ✅ PASS | Works when called directly (unused by tools) |
| `GET_TASK_LOGS` | ✅ PASS | — |
| `GET_TASK_TEST_RESULTS` | ✅ PASS | — |
| `GET_INFERRED_PROJECT_IDS` | ❌ FAIL | `Cannot query field "projectIdentifier" on type "Patch"` |

## Current Code Context

### Root Cause: `projectIdentifier` → `projectMetadata.identifier`

**Evergreen schema change**: The `Patch` type no longer has a top-level `projectIdentifier` field. Instead, project identity is available via the `projectMetadata` field, which returns a `Project` type containing `identifier`.

**Before (broken)**:
```graphql
patch {
  projectIdentifier    # ❌ Field no longer exists on Patch
}
```

**After (fixed)**:
```graphql
patch {
  projectMetadata {    # ✅ Returns Project type
    identifier         # ✅ The project identifier string
  }
}
```

### Secondary Change: `Patch.version` is now `VersionLite`

**Before (broken)**:
```graphql
patch {
  version              # ❌ Was a scalar/string, now VersionLite requires subfields
}
```

**After (fixed)**:
```graphql
patch {
  version {            # ✅ VersionLite requires subfield selection
    id
    status
  }
}
```

### Data Flow Impact

The change ripples through the entire data pipeline:

1. **Query layer** (`evergreen_queries.py`): 3 queries request `projectIdentifier` on Patch — must change to `projectMetadata { identifier }`
2. **Client layer** (`evergreen_graphql_client.py`): Returns raw dicts — no code changes needed (just pass through)
3. **Business logic layer** (`failed_jobs_tools.py`): Consumes `patch.get("projectIdentifier")` — must change to `patch.get("projectMetadata", {}).get("identifier")`
4. **Dead code** (`GET_PROJECT_PATCHES`): Uses bare `version` field — must add subfield selection or remove

### Files That Need Changes

| File | Change Category | Scope |
|------|----------------|-------|
| `src/evergreen_mcp/evergreen_queries.py` | Query string updates | 3 queries + 1 dead query |
| `src/evergreen_mcp/failed_jobs_tools.py` | Result field access | 3 functions |
| `tests/test_failed_jobs_tools.py` | Mock data shape | Multiple test fixtures |
| `tests/test_project_inference.py` | Mock data shape | Multiple test fixtures |
| `tests/test_graphql_live_queries.py` | **NEW** — Integration tests | 9 test classes, one per active query |

## Proposed Changes

### Change 1: Update `GET_USER_RECENT_PATCHES` query (evergreen_queries.py L106-L134)

Replace `projectIdentifier` with `projectMetadata { identifier }`:

```graphql
query GetUserRecentPatches($userId: String!, $limit: Int = 10, $page: Int = 0) {
  user(userId: $userId) {
    patches(patchesInput: {
      limit: $limit
      page: $page
      patchName: ""
      statuses: []
      includeHidden: false
    }) {
      patches {
        id
        githash
        description
        author
        authorDisplayName
        status
        createTime
        patchNumber
        projectMetadata {
          identifier
        }
        versionFull {
          id
          status
        }
      }
    }
  }
}
```

### Change 2: Update `GET_PATCH_FAILED_TASKS` query (evergreen_queries.py L137-L193)

Replace `projectIdentifier` with `projectMetadata { identifier }`:

```graphql
query GetPatchFailedTasks($patchId: String!) {
  patch(patchId: $patchId) {
    id
    githash
    description
    author
    authorDisplayName
    status
    createTime
    patchNumber
    projectMetadata {
      identifier
    }
    versionFull {
      id
      revision
      author
      createTime
      status
      tasks(options: {
        statuses: ["failed", "system-failed", "task-timed-out"]
        limit: 100
      }) {
        count
        data {
          id
          displayName
          buildVariant
          status
          execution
          finishTime
          timeTaken
          hasTestResults
          failedTestCount
          totalTestCount
          ami
          hostId
          distroId
          imageId
          details {
            description
            status
            timedOut
            timeoutType
            failingCommand
          }
          logs {
            taskLogLink
            agentLogLink
            systemLogLink
            allLogLink
          }
        }
      }
    }
  }
}
```

### Change 3: Update `GET_INFERRED_PROJECT_IDS` query (evergreen_queries.py L315-L335)

Replace `projectIdentifier` with `projectMetadata { identifier }`:

```graphql
query InferredProjectIds($userId: String!, $limit: Int = 50, $page: Int = 0) {
  user(userId: $userId) {
    patches(
      patchesInput: {
        limit: $limit
        page: $page
        includeHidden: false
        patchName: ""
        statuses: []
      }
    ) {
      patches {
        id
        createTime
        projectMetadata {
          identifier
        }
      }
    }
  }
}
```

### Change 4: Update `GET_PROJECT_PATCHES` dead query (evergreen_queries.py L76-L91)

This query is **never imported and never used**. Two options:
- **Option A (recommended)**: Delete the query entirely as dead code.
- **Option B**: Fix it by adding `version { id status }` subfields.

If we keep it, the fix would be:
```graphql
query GetProjectPatches($projectId: String!, $limit: Int = 10) {
  project(projectIdentifier: $projectId) {
    patches(patchesInput: {limit: $limit}) {
      patches {
        id
        description
        author
        createTime
        status
        version {
          id
          status
        }
      }
    }
  }
}
```

### Change 5: Update `failed_jobs_tools.py` field access

Three functions access `patch.get("projectIdentifier")`. All must change to navigate the nested structure.

#### 5a. `fetch_user_recent_patches()` (L54-L55)

**Before**:
```python
if project_id and patch.get("projectIdentifier") != project_id:
```

**After**:
```python
if project_id and patch.get("projectMetadata", {}).get("identifier") != project_id:
```

Also at L81 where the field is extracted:
**Before**:
```python
"project_identifier": patch.get("projectIdentifier"),
```
**After**:
```python
"project_identifier": patch.get("projectMetadata", {}).get("identifier"),
```

#### 5b. `fetch_patch_failed_jobs()` (L152, L234)

**Before** (L152):
```python
if project_id and patch.get("projectIdentifier") != project_id:
    raise ValueError(...)
```

**After**:
```python
if project_id and patch.get("projectMetadata", {}).get("identifier") != project_id:
    raise ValueError(...)
```

**Before** (L234):
```python
"project_identifier": patch.get("projectIdentifier"),
```

**After**:
```python
"project_identifier": patch.get("projectMetadata", {}).get("identifier"),
```

#### 5c. `fetch_inferred_project_ids()` (L453)

**Before**:
```python
project_id = patch.get("projectIdentifier")
```

**After**:
```python
project_id = patch.get("projectMetadata", {}).get("identifier")
```

### Change 6: Update test mock data shapes

#### 6a. `tests/test_failed_jobs_tools.py`

All mock patch objects that include `"projectIdentifier": "some-project"` must change to:
```python
"projectMetadata": {"identifier": "some-project"}
```

Specific locations to update (exact line numbers to be verified during implementation):
- Mock data in `test_fetch_user_recent_patches_*` tests
- Mock data in `test_fetch_patch_failed_jobs_*` tests
- Mock data in `test_fetch_inferred_project_ids_*` tests

#### 6b. `tests/test_project_inference.py`

Mock data for `get_inferred_project_ids` returns patches with `"projectIdentifier"` — must change to `"projectMetadata": {"identifier": ...}`.

Field access in test assertions that check `result["projects"][i]["project_identifier"]` remain unchanged (the `fetch_inferred_project_ids` function still outputs `project_identifier` as its key).

### Change 7: Add integration tests — `tests/test_graphql_live_queries.py` (NEW FILE)

Create a new pytest integration test file that exercises **every GraphQL query** against the live Evergreen API. This catches schema regressions early and is repeatable.

**Test design principles**:
- Marked with `@pytest.mark.integration` + `RUN_INTEGRATION_TESTS=1` gate (same pattern as `test_mcp_client.py`)
- Uses the `evergreen` CLI to get an OAuth token (`evergreen client get-oauth-token`)
- Sends raw HTTP POST requests to the GraphQL endpoint — does NOT go through the `EvergreenGraphQLClient` class (tests the queries themselves, not our client wrapper)
- Each test executes one query constant from `evergreen_queries.py` and asserts:
  1. No `errors` key in response (schema validation)
  2. The expected `data` shape exists (non-null, correct nesting)
  3. Specific field values are present and have expected types
- Uses well-known test fixtures: the `evergreen` project, patch `6a3c95198972470007910a4d`, and a task ID derived from that patch at runtime

**Test cases**:

```python
# tests/test_graphql_live_queries.py

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
        # No GraphQL errors
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
```

**Why this approach**:
- Tests the **actual query strings** from `evergreen_queries.py` — if a field name is wrong or missing, the test fails with the exact GraphQL validation error
- Uses `aiohttp` directly (already a dependency) rather than the `gql` library wrapper — eliminates client bugs as a confounding factor
- Session-scoped fixtures for token + HTTP session — avoids re-auth on every test
- Derives user_id from the JWT the same way the real code does
- Same skip gate as existing integration tests (`RUN_INTEGRATION_TESTS=1`)

### Change 8: Optional cleanup — remove dead queries

Consider removing `GET_PROJECT_PATCHES` and `GET_PROJECT_BUILDS` from `evergreen_queries.py` since they are never imported or used. Also consider removing the unused `GET_PROJECT` and `GET_PROJECT_SETTINGS` client methods, though this is lower priority and can be done separately.

## Verification Plan

1. **Integration tests (automated)**: Run `RUN_INTEGRATION_TESTS=1 pytest tests/test_graphql_live_queries.py -v` to confirm:
   - Every query string in `evergreen_queries.py` is accepted by the live Evergreen GraphQL schema
   - The response shape matches what `failed_jobs_tools.py` expects (especially `projectMetadata.identifier`)
   - No regressions in the previously-working queries (`GET_PROJECTS`, `GET_TASK_LOGS`, `GET_TASK_TEST_RESULTS`, `GET_VERSION_WITH_FAILED_TASKS`)

2. **Unit tests**: Run `pytest tests/ -v --ignore=tests/test_graphql_live_queries.py` to confirm all mock-based tests pass with updated data shapes.

3. **No-regression for working queries**: The integration test file covers all 9 active queries. The 2 dead queries (`GET_PROJECT_PATCHES`, `GET_PROJECT_BUILDS`) are excluded since they are removed in Change 4.

4. **End-to-end MCP tool validation (manual, post-merge)**: Use the MCP server directly to exercise the tool flows:
   - `list_user_recent_patches_evergreen` with and without `project_id` filtering
   - `get_patch_failed_jobs_evergreen` with the patch ID `6a3c95198972470007910a4d`
   - `get_inferred_project_ids_evergreen`
   - `get_task_log_summary` with a known task ID
   - `get_test_results_summary` with a known task ID

## Risks / Open Questions

| # | Risk / Question | Mitigation / Answer |
|---|----------------|---------------------|
| 1 | **`projectMetadata` could be null for some patches?** | The schema shows `projectMetadata: Project` (no `!`), so it could theoretically be null. Using `.get("projectMetadata", {}).get("identifier")` handles this gracefully, returning `None` for patches without project metadata. The existing code already handles `None` projectIdentifier in filter logic. |
| 2 | **Are there other schema changes we haven't noticed?** | All 11 queries have been tested against the live API. Only the 3 `projectIdentifier` queries and the `version` subfield issue were found. No other field-level breakages exist. |
| 3 | **Should the unused queries be removed now?** | Recommended as a separate follow-up to keep this change focused on the breaking schema fix. The dead queries (`GET_PROJECT_PATCHES`, `GET_PROJECT_BUILDS`) don't affect runtime. |
| 4 | **`GET_PROJECT_PATCHES` has `version` that now requires subfields — but it's unused. Should we fix or remove?** | Remove it. It's never imported, never used, and the `version` field returning `VersionLite` is a secondary issue. Removing dead code is cleaner. |
| 5 | **User ID format mismatch**: The OIDC endpoint uses `rob.george` as userId, not `rob.george@mongodb.com`. The `_user_from_jwt` function already strips the domain, so this is handled. However, the API key endpoint may use a different user ID format. | Existing code handles this correctly via `_user_from_jwt`. No change needed. |

## Relevant Files / Research References

### Lucky-Star (this repo)
- `src/evergreen_mcp/evergreen_queries.py` — All GraphQL query strings (L1-L335)
- `src/evergreen_mcp/evergreen_graphql_client.py` — Client that executes queries (L1-L435)
- `src/evergreen_mcp/failed_jobs_tools.py` — Business logic consuming query results (L1-L663)
- `src/evergreen_mcp/mcp_tools.py` — MCP tool definitions (L1-L587)
- `tests/test_failed_jobs_tools.py` — Unit tests with mocked GraphQL results
- `tests/test_project_inference.py` — Unit tests for project inference

### Evergreen (reference repo)
- `graphql/schema/types/patch.graphql` — Patch type definition (`projectMetadata: Project` at L90, no `projectIdentifier`)
- `graphql/schema/types/version.graphql` — Version + VersionLite type definitions
- `graphql/schema/types/project.graphql` — Project type with `identifier` field
- `graphql/patch_resolver.go` — Patch resolvers (projectMetadata, versionFull, etc.)

### Research Artifacts
- `_findings/codebase-research-evergreen-schema.md` — Full evergreen schema analysis
- `_findings/codebase-research-lucky-star-queries.md` — Full query-by-query usage analysis
