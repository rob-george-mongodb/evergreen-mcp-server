# Codebase Research: Lucky-Star GraphQL Query Usage

## Research Question
Map all GraphQL queries defined in `evergreen_queries.py`, document exactly which fields each requests, trace how results are consumed through the client layer and tool layer, and identify any unused queries or fields.

---

## Search Trail

| # | Search Query / Pattern | Files Found | Notes |
|---|------------------------|-------------|-------|
| 1 | Read `src/evergreen_mcp/evergreen_queries.py` | 1 file | All 11 query constant definitions |
| 2 | Read `src/evergreen_mcp/evergreen_graphql_client.py` | 1 file | Client methods that execute queries and consume results |
| 3 | Read `src/evergreen_mcp/mcp_tools.py` | 1 file | MCP tool definitions that call client methods |
| 4 | Read `src/evergreen_mcp/failed_jobs_tools.py` | 1 file | Business logic layer that transforms query results |
| 5 | Read `src/evergreen_mcp/artifact_download_tools.py` | 1 file | REST-only, no GraphQL usage |
| 6 | Read `src/evergreen_mcp/server.py` | 1 file | Server setup + `evergreen://projects` resource uses GraphQL directly |
| 7 | Read `src/evergreen_mcp/models.py` | 1 file | Pydantic models for REST responses, not GraphQL |
| 8 | Read `src/evergreen_mcp/evergreen_rest_client.py` | 1 file | REST client (no GraphQL) |
| 9 | Read `tests/test_failed_jobs_tools.py` | 1 file | Tests that mock GraphQL client returns |
| 10 | Read `tests/test_project_inference.py` | 1 file | Tests for project inference (GraphQL consumer) |
| 11 | Read `tests/test_mcp_client.py` | 1 file | Integration test, no direct GraphQL assertions |
| 12 | Read `tests/test_evergreen_rest_client.py` | 1 file | REST client tests only |
| 13 | Read `tests/test_artifact_download_tools.py` | 1 file | REST-only tests |
| 14 | Grep for `GET_PROJECT_PATCHES\|GET_PROJECT_BUILDS` | 0 additional consumers | These queries are defined but **never imported or used** |

---

## Relevant Files

| # | File Path | Relevance | Key Lines |
|---|-----------|-----------|-----------|
| 1 | `src/evergreen_mcp/evergreen_queries.py` | Defines all 11 GraphQL query strings with every requested field | L1-L335 (entire file) |
| 2 | `src/evergreen_mcp/evergreen_graphql_client.py` | Executes queries; extracts and returns result dicts | L207-L424 (public methods) |
| 3 | `src/evergreen_mcp/failed_jobs_tools.py` | Transforms GraphQL results into structured tool output | L20-L663 (entire file) |
| 4 | `src/evergreen_mcp/mcp_tools.py` | MCP tool layer; orchestrates client calls + result formatting | L91-L587 |
| 5 | `src/evergreen_mcp/server.py` | Server lifecycle; `evergreen://projects` resource consumes `get_projects()` directly | L352-L370 |
| 6 | `src/evergreen_mcp/models.py` | Pydantic models for REST API responses only; **not used by GraphQL path** | L1-L123 |
| 7 | `tests/test_failed_jobs_tools.py` | Unit tests that mock GraphQL client return shapes | L1-L328 |
| 8 | `tests/test_project_inference.py` | Unit tests for project inference (consumes `GET_INFERRED_PROJECT_IDS` results) | L1-L120 |

---

## Detailed Query-by-Query Analysis

### Query 1: `GET_PROJECTS`

**Query String** (L9-L24):
```graphql
query GetProjects {
  projects {
    groupDisplayName
    projects {
      id
      displayName
      identifier
      enabled
      owner
      repo
      branch
    }
  }
}
```
**Variables**: None

**Client Method**: `EvergreenGraphQLClient.get_projects()` (evergreen_graphql_client.py:L207-L221)
- Executes `GET_PROJECTS`
- **Result consumption**: Extracts `result.get("projects", [])` — a list of group objects
- **Transformation**: Flattens grouped structure — iterates each group, extends a flat list with `group.get("projects", [])`. The `groupDisplayName` field is **requested but discarded** (never returned).
- **Returns**: `List[Dict]` — flat list of project dicts with keys: `id`, `displayName`, `identifier`, `enabled`, `owner`, `repo`, `branch`

**Upstream Consumers**:
1. **`mcp_tools.py`**: No direct MCP tool calls `get_projects()`.
2. **`server.py` L352-L370**: The `evergreen://projects` MCP resource calls `evg_ctx.client.get_projects()` and further transforms the result, extracting only: `id`, `identifier`, `displayName`, `enabled`, `owner`, `repo`. The `branch` field is **requested by the query and returned by the client, but then discarded by the resource**.

---

### Query 2: `GET_PROJECT`

**Query String** (L27-L44):
```graphql
query GetProject($projectId: String!) {
  project(projectIdentifier: $projectId) {
    id
    displayName
    identifier
    enabled
    owner
    repo
    branch
    admins
    banner {
      text
      theme
    }
  }
}
```
**Variables**: `projectId: String!`

**Client Method**: `EvergreenGraphQLClient.get_project()` (evergreen_graphql_client.py:L223-L242)
- Executes `GET_PROJECT` with `{"projectId": project_id}`
- **Result consumption**: `result.get("project")` — returns the entire project dict as-is, no transformation
- **Returns**: `Dict[str, Any]` with keys: `id`, `displayName`, `identifier`, `enabled`, `owner`, `repo`, `branch`, `admins`, `banner{ text, theme }`

**Upstream Consumers**: **None**. This method is not called by any MCP tool, any function in `failed_jobs_tools.py`, or any other module. The query and client method exist but are unused.

---

### Query 3: `GET_PROJECT_SETTINGS`

**Query String** (L47-L73):
```graphql
query GetProjectSettings($projectId: String!) {
  projectSettings(projectIdentifier: $projectId) {
    projectRef {
      id
      identifier
      displayName
      enabled
      owner
      repo
      branch
    }
    githubWebhooksEnabled
    vars {
      adminOnlyVars
      privateVars
      vars
    }
    aliases {
      alias
      gitTag
      variant
      task
    }
  }
}
```
**Variables**: `projectId: String!`

**Client Method**: `EvergreenGraphQLClient.get_project_settings()` (evergreen_graphql_client.py:L244-L261)
- Executes `GET_PROJECT_SETTINGS` with `{"projectId": project_id}`
- **Result consumption**: `result.get("projectSettings")` — returns the entire settings dict as-is, no transformation
- **Returns**: `Dict[str, Any]` with nested keys: `projectRef{...}`, `githubWebhooksEnabled`, `vars{ adminOnlyVars, privateVars, vars }`, `aliases[{ alias, gitTag, variant, task }]`

**Upstream Consumers**: **None**. This method is not called by any MCP tool or any other module. Unused.

---

### Query 4: `GET_PROJECT_PATCHES`

**Query String** (L76-L91):
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
        version
      }
    }
  }
}
```
**Variables**: `projectId: String!`, `limit: Int`

**Client Method**: **None**. This query is defined in `evergreen_queries.py` but is **not imported** by `evergreen_graphql_client.py` and has no corresponding client method. Completely unused.

---

### Query 5: `GET_PROJECT_BUILDS`

**Query String** (L94-L103):
```graphql
query GetProjectBuilds($projectId: String!, $limit: Int = 10) {
  project(projectIdentifier: $projectId) {
    id
    displayName
    # Note: This would need to be adjusted based on actual schema structure
    # The merged-schema.graphql should be consulted for exact field names
  }
}
```
**Variables**: `projectId: String!`, `limit: Int`

**Client Method**: **None**. This query is defined but **not imported** and has no client method. The query is also **incomplete** (has a comment noting it needs schema adjustment). Completely unused.

---

### Query 6: `GET_USER_RECENT_PATCHES`

**Query String** (L106-L134):
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
        projectIdentifier
        versionFull {
          id
          status
        }
      }
    }
  }
}
```
**Variables**: `userId: String!`, `limit: Int` (capped to max 50), `page: Int`

**Client Method**: `EvergreenGraphQLClient.get_user_recent_patches()` (evergreen_graphql_client.py:L263-L288)
- Executes `GET_USER_RECENT_PATCHES` with capped limit
- **Result consumption**: `result.get("user", {}).get("patches", {}).get("patches", [])`
- **Transformation**: Returns the raw list of patch dicts from the API with no transformation at the client level
- **Returns**: `List[Dict]` with keys: `id`, `githash`, `description`, `author`, `authorDisplayName`, `status`, `createTime`, `patchNumber`, `projectIdentifier`, `versionFull{ id, status }`

**Upstream Consumer**: `failed_jobs_tools.fetch_user_recent_patches()` (L20-L90)
- **Field access and transformation**:
  - `patch.get("id")` → `patch_id`
  - `patch.get("patchNumber")` → `patch_number`
  - `patch.get("githash")` → `githash` (kept as-is)
  - `patch.get("description")` → `description` (kept as-is)
  - `patch.get("author")` → `author` (kept as-is)
  - `patch.get("authorDisplayName")` → `author_display_name` (renamed to snake_case)
  - `patch.get("status")` → `status` (kept as-is)
  - `patch.get("createTime")` → `create_time` (renamed to snake_case)
  - `patch.get("projectIdentifier")` → `project_identifier` (renamed to snake_case)
  - `patch.get("versionFull") is not None` → `has_version` (boolean derived)
  - `patch.get("versionFull", {}).get("status")` → `version_status` (nested field extraction)
- **Optional filtering**: If `project_id` is provided, patches where `patch.get("projectIdentifier") != project_id` are **filtered out** (L54-L55)
- **Pagination metadata**: Adds `has_more` (inferred from `len(patches) == page_size`), `next_page`, `count`, `page`, `page_size`

**MCP Tool**: `list_user_recent_patches_evergreen` (mcp_tools.py:L106-L204)
- Calls `fetch_user_recent_patches(client, user_id, limit, project_id=effective_project_id)`
- Also calls `infer_project_id_from_context()` if `project_id` is not provided (which itself uses `GET_INFERRED_PROJECT_IDS`)
- Returns `json.dumps(result)` with optional `emit_message` / `project_detection` wrapper for low-confidence inference

---

### Query 7: `GET_PATCH_FAILED_TASKS`

**Query String** (L137-L193):
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
    projectIdentifier
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
**Variables**: `patchId: String!`

**Client Method**: `EvergreenGraphQLClient.get_patch_failed_tasks()` (evergreen_graphql_client.py:L290-L311)
- Executes `GET_PATCH_FAILED_TASKS` with `{"patchId": patch_id}`
- **Result consumption**: `result.get("patch")` — returns the entire patch dict as-is
- Logs `version.get("tasks", {}).get("count", 0)` for info
- **Returns**: `Dict[str, Any]` — the raw patch object with nested `versionFull` containing `tasks`

**Upstream Consumer**: `failed_jobs_tools.fetch_patch_failed_jobs()` (L93-L235)
- **Patch-level field access**:
  - `patch.get("id")` → `patch_id`
  - `patch.get("patchNumber")` → `patch_number`
  - `patch.get("githash")` → `githash`
  - `patch.get("description")` → `description`
  - `patch.get("author")` → `author`
  - `patch.get("authorDisplayName")` → `author_display_name`
  - `patch.get("status")` → `status`
  - `patch.get("createTime")` → `create_time`
  - `patch.get("projectIdentifier")` → `project_identifier`
- **Version-level field access** (`version = patch.get("versionFull", {})`):
  - `version.get("id")` → `version_id`
  - `version.get("revision")` → `revision`
  - `version.get("author")` → `author`
  - `version.get("createTime")` → `create_time`
  - `version.get("status")` → `status`
- **Task-level field access** (iterates `tasks_data.get("data", [])`):
  - `task.get("id")` → `task_id`
  - `task.get("displayName")` → `task_name`
  - `task.get("buildVariant")` → `build_variant`
  - `task.get("status")` → `status`
  - `task.get("execution", 0)` → `execution`
  - `task.get("finishTime")` → `finish_time`
  - `task.get("timeTaken")` → `duration_ms`
  - `task.get("ami")` → `ami`
  - `task.get("hostId")` → `host_id`
  - `task.get("distroId")` → `distro_id`
  - `task.get("imageId")` → `image_id`
- **Details sub-object** (`task.get("details", {})`):
  - `details.get("description")` → `failure_details.description`
  - `details.get("timedOut", False)` → `failure_details.timed_out`
  - `details.get("timeoutType")` → `failure_details.timeout_type`
  - `details.get("failingCommand")` → `failure_details.failing_command`
  - Also sets `has_timeouts = True` if any task has `timedOut`
- **Logs sub-object** (`task.get("logs", {})`):
  - `logs.get("taskLogLink")` → `logs.task_log`
  - `logs.get("agentLogLink")` → `logs.agent_log`
  - `logs.get("systemLogLink")` → `logs.system_log`
  - `logs.get("allLogLink")` → `logs.all_logs`
- **Test info** (conditional):
  - `task.get("hasTestResults", False)` → determines whether `test_info` block is populated
  - `task.get("failedTestCount", 0)` → `test_info.failed_test_count`
  - `task.get("totalTestCount", 0)` → `test_info.total_test_count`
- **Summary construction**:
  - `total_count` from `tasks_data.get("count", 0)`
  - `returned_tasks` = len(processed_tasks)
  - `failed_build_variants` = unique sorted set of build variant names
  - `has_timeouts` boolean flag
- **Validation**: If `project_id` is provided, checks `patch.get("projectIdentifier") != project_id` and raises `ValueError`

**MCP Tool**: `get_patch_failed_jobs_evergreen` (mcp_tools.py:L218-L306)
- Calls `fetch_patch_failed_jobs(client, patch_id, max_results, project_id=effective_project_id)`
- Also calls `infer_project_id_from_context()` if `project_id` is not provided
- Returns `json.dumps(result)` with optional inference metadata

**All requested fields are consumed.** No field from this query is discarded.

---

### Query 8: `GET_VERSION_WITH_FAILED_TASKS`

**Query String** (L196-L241):
```graphql
query GetVersionWithFailedTasks($versionId: String!) {
  version(versionId: $versionId) {
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
```
**Variables**: `versionId: String!`

**Client Method**: `EvergreenGraphQLClient.get_version_with_failed_tasks()` (evergreen_graphql_client.py:L313-L333)
- Executes `GET_VERSION_WITH_FAILED_TASKS` with `{"versionId": version_id}`
- **Result consumption**: `result.get("version")` — returns the version dict as-is
- Logs `version.get("tasks", {}).get("count", 0)`
- **Returns**: `Dict[str, Any]` — the raw version object

**Upstream Consumers**: **None**. This method is not called by any MCP tool or any function in `failed_jobs_tools.py`. The current tooling always goes through the patch path (`GET_PATCH_FAILED_TASKS`) rather than querying versions directly. **Unused at the tool layer**, though it is imported and has a client method.

---

### Query 9: `GET_TASK_LOGS`

**Query String** (L244-L266):
```graphql
query GetTaskLogs($taskId: String!, $execution: Int!) {
  task(taskId: $taskId, execution: $execution) {
    id
    displayName
    execution
    ami
    hostId
    distroId
    imageId
    taskLogs {
      taskId
      execution
      taskLogs {
        severity
        message
        timestamp
        type
      }
    }
  }
}
```
**Variables**: `taskId: String!`, `execution: Int!`

**Client Method**: `EvergreenGraphQLClient.get_task_logs()` (evergreen_graphql_client.py:L335-L354)
- Executes `GET_TASK_LOGS` with `{"taskId": task_id, "execution": execution}`
- **Result consumption**: `result.get("task")` — returns the task dict as-is
- Logs count of `task.get("taskLogs", {}).get("taskLogs", [])`
- **Returns**: `Dict[str, Any]` — the raw task object including nested `taskLogs`

**Upstream Consumer**: `failed_jobs_tools.fetch_task_logs()` (L238-L285)
- **Task-level field access**:
  - `task_data.get("displayName")` → `task_name`
  - `task_data.get("ami")` → `ami`
  - `task_data.get("hostId")` → `host_id`
  - `task_data.get("distroId")` → `distro_id`
  - `task_data.get("imageId")` → `image_id`
- **Logs extraction**: `task_data.get("taskLogs", {}).get("taskLogs", [])` → raw log list
- **Log processing** via `process_logs()` (L389-L428):
  - Each log entry has: `severity`, `message`, `timestamp`, `type`
  - If `filter_errors=True`: keeps only entries where `severity in ["error", "fatal"]` OR message contains `"error"`, `"fail"`, or `"exception"`
  - Sorts by `timestamp`
  - Truncates to `max_lines`
- **Note**: `task_data.get("id")` and `task_data.get("execution")` from the query response are **not consumed** by `fetch_task_logs()` — instead it uses the `task_id` and `execution` from the arguments. The nested `taskLogs.taskId` and `taskLogs.execution` are also not consumed.
- **Returns**: Dict with `task_id`, `execution`, `task_name`, `log_type`, `total_lines`, `logs`, `truncated`, `ami`, `host_id`, `distro_id`, `image_id`

**MCP Tool**: `get_task_log_summary` (mcp_tools.py:L318-L361)
- Calls `fetch_task_logs(client, arguments)` where arguments contain `task_id`, `execution`, `max_lines`, `filter_errors`
- Returns `json.dumps(result)`

---

### Query 10: `GET_TASK_TEST_RESULTS`

**Query String** (L269-L312):
```graphql
query GetTaskTestResults(
  $taskId: String!,
  $execution: Int!,
  $testFilterOptions: TestFilterOptions
) {
  task(taskId: $taskId, execution: $execution) {
    id
    displayName
    buildVariant
    status
    execution
    hasTestResults
    failedTestCount
    totalTestCount
    ami
    hostId
    distroId
    imageId
    tests(opts: $testFilterOptions) {
      totalTestCount
      filteredTestCount
      testResults {
        id
        status
        testFile
        duration
        startTime
        endTime
        exitCode
        groupID
        logs {
          url
          urlParsley
          urlRaw
          lineNum
          renderingType
          version
        }
      }
    }
  }
}
```
**Variables**: `taskId: String!`, `execution: Int!`, `testFilterOptions: TestFilterOptions`
- `testFilterOptions` is built by the client: `{"limit": limit, "page": 0}` and optionally `{"statuses": ["fail", "failed"]}` when `failed_only=True`

**Client Method**: `EvergreenGraphQLClient.get_task_test_results()` (evergreen_graphql_client.py:L356-L395)
- Executes `GET_TASK_TEST_RESULTS` with constructed variables
- **Result consumption**: `result.get("task")` — returns the task dict as-is
- Logs `test_results.get("filteredTestCount", 0)`
- **Returns**: `Dict[str, Any]` — the raw task object including nested `tests`

**Upstream Consumer**: `failed_jobs_tools.fetch_task_test_results()` (L288-L386)
- **Task-level field access**:
  - `task_data.get("id")` → `task_info.task_id`
  - `task_data.get("displayName")` → `task_info.task_name`
  - `task_data.get("buildVariant")` → `task_info.build_variant`
  - `task_data.get("status")` → `task_info.status`
  - `task_data.get("execution")` → `task_info.execution`
  - `task_data.get("hasTestResults", False)` → `task_info.has_test_results`
  - `task_data.get("failedTestCount", 0)` → `task_info.failed_test_count`
  - `task_data.get("totalTestCount", 0)` → `task_info.total_test_count`
  - `task_data.get("ami")` → `task_info.ami`
  - `task_data.get("hostId")` → `task_info.host_id`
  - `task_data.get("distroId")` → `task_info.distro_id`
  - `task_data.get("imageId")` → `task_info.image_id`
- **Tests extraction** (`test_results_data = task_data.get("tests", {})`):
  - `test_results_data.get("totalTestCount", 0)` → `summary.total_test_results`
  - `test_results_data.get("filteredTestCount", 0)` → `summary.filtered_test_count`
- **Per-test-result field access** (iterates `test_results` list):
  - `test.get("id")` → `test_id`
  - `test.get("testFile")` → `test_file`
  - `test.get("status")` → `status`
  - `test.get("duration")` → `duration`
  - `test.get("startTime")` → `start_time`
  - `test.get("endTime")` → `end_time`
  - `test.get("exitCode")` → `exit_code`
  - `test.get("groupID")` → `group_id`
  - **Logs sub-object** (`test.get("logs", {})`):
    - `logs.get("url")` → `logs.url`
    - `logs.get("urlParsley")` → `logs.url_parsley`
    - `logs.get("urlRaw")` → `logs.url_raw`
    - `logs.get("lineNum")` → `logs.line_num`
    - `logs.get("renderingType")` → `logs.rendering_type`
    - `logs.get("version")` → `logs.version`
- **Failed test counting**: Re-counts tests with `status.lower() in ["fail", "failed"]` → `summary.failed_tests_in_results`
- **Returns**: Dict with `task_info`, `test_results`, `summary`

**MCP Tool**: `get_test_results_summary` (mcp_tools.py:L372-L415)
- Calls `fetch_task_test_results(client, arguments)`
- Returns `json.dumps(result)`

---

### Query 11: `GET_INFERRED_PROJECT_IDS`

**Query String** (L315-L335):
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
        projectIdentifier
      }
    }
  }
}
```
**Variables**: `userId: String!`, `limit: Int` (capped to max 50), `page: Int`

**Client Method**: `EvergreenGraphQLClient.get_inferred_project_ids()` (evergreen_graphql_client.py:L397-L424)
- Executes `GET_INFERRED_PROJECT_IDS` with capped limit
- **Result consumption**: `result.get("user", {}).get("patches", {}).get("patches", [])`
- **Returns**: `List[Dict]` with keys: `id`, `createTime`, `projectIdentifier`

**Upstream Consumers**:

1. `failed_jobs_tools.fetch_inferred_project_ids()` (L431-L502)
   - Iterates patches; extracts `patch.get("projectIdentifier")` and `patch.get("createTime")`
   - `patch.get("id")` is **requested by the query but never consumed**
   - Aggregates: counts patches per project, tracks latest `createTime` per project
   - Sorts by `-patch_count` then `latest_patch_time`
   - Returns: `{"user_id", "projects": [{"project_identifier", "patch_count", "latest_patch_time"}], "total_projects", "patches_scanned", "max_patches"}`

2. `failed_jobs_tools.infer_project_id_from_context()` (L534-L612)
   - Calls `fetch_inferred_project_ids(client, user_id, max_patches)`
   - Logic:
     - 0 projects → `confidence="none"`, `source="user_selection_required"`
     - 1 project → `confidence="high"`, `source="single_project"`
     - Multiple projects → picks the one with the most recent `latest_patch_time`, `confidence="low"`, `source="most_recent_fallback"`

**MCP Tools**:
- `get_inferred_project_ids_evergreen` (mcp_tools.py:L425-L447) — calls `fetch_inferred_project_ids()` directly
- `list_user_recent_patches_evergreen` — calls `infer_project_id_from_context()` when `project_id` is not provided
- `get_patch_failed_jobs_evergreen` — calls `infer_project_id_from_context()` when `project_id` is not provided

---

## Code Path Map

### Path A: User Recent Patches (primary flow)
```
MCP Tool: list_user_recent_patches_evergreen
  ├─ (if no project_id) → infer_project_id_from_context()
  │    └─ fetch_inferred_project_ids()
  │         └─ EvergreenGraphQLClient.get_inferred_project_ids()
  │              └─ _execute_query(GET_INFERRED_PROJECT_IDS)
  │                   └─ GraphQL response → extract user.patches.patches[]
  │                        → aggregate by projectIdentifier, createTime
  ├─ fetch_user_recent_patches()
  │    └─ EvergreenGraphQLClient.get_user_recent_patches()
  │         └─ _execute_query(GET_USER_RECENT_PATCHES)
  │              └─ GraphQL response → extract user.patches.patches[]
  │                   → filter by project_id, rename camelCase→snake_case
  └─ json.dumps(result)
```

### Path B: Failed Jobs for Patch
```
MCP Tool: get_patch_failed_jobs_evergreen
  ├─ (if no project_id) → infer_project_id_from_context() [same as Path A]
  ├─ fetch_patch_failed_jobs()
  │    └─ EvergreenGraphQLClient.get_patch_failed_tasks()
  │         └─ _execute_query(GET_PATCH_FAILED_TASKS)
  │              └─ GraphQL response → extract patch{}
  │                   → extract patch metadata + versionFull.tasks.data[]
  │                        → per-task: extract id, displayName, buildVariant, status,
  │                          execution, finishTime, timeTaken, ami, hostId, distroId,
  │                          imageId, details{}, logs{}, hasTestResults, failedTestCount,
  │                          totalTestCount
  └─ json.dumps(result)
```

### Path C: Task Logs (GraphQL path)
```
MCP Tool: get_task_log_summary
  └─ fetch_task_logs()
       └─ EvergreenGraphQLClient.get_task_logs()
            └─ _execute_query(GET_TASK_LOGS)
                 └─ GraphQL response → extract task{}
                      → extract displayName, ami, hostId, distroId, imageId
                      → extract taskLogs.taskLogs[] → filter/sort/truncate
  └─ json.dumps(result)
```

### Path D: Task Test Results (GraphQL path)
```
MCP Tool: get_test_results_summary
  └─ fetch_task_test_results()
       └─ EvergreenGraphQLClient.get_task_test_results()
            └─ _execute_query(GET_TASK_TEST_RESULTS)
                 └─ GraphQL response → extract task{}
                      → extract task metadata + tests.testResults[]
                      → per-test: extract id, status, testFile, duration, startTime,
                        endTime, exitCode, groupID, logs{}
  └─ json.dumps(result)
```

### Path E: Project IDs Inference
```
MCP Tool: get_inferred_project_ids_evergreen
  └─ fetch_inferred_project_ids()
       └─ EvergreenGraphQLClient.get_inferred_project_ids()
            └─ _execute_query(GET_INFERRED_PROJECT_IDS)
                 └─ GraphQL response → extract user.patches.patches[]
                      → aggregate by projectIdentifier → count + latest createTime
  └─ json.dumps(result)
```

### Path F: Project Resource (MCP resource, not tool)
```
MCP Resource: evergreen://projects
  └─ EvergreenGraphQLClient.get_projects()
       └─ _execute_query(GET_PROJECTS)
            └─ GraphQL response → extract projects[] → flatten groups
                 → further filter to only: id, identifier, displayName, enabled, owner, repo
  └─ json.dumps(result)
```

### Path G: REST-based tools (no GraphQL)
```
MCP Tool: get_task_log_detailed → fetch_evergreen_task_logs() → EvergreenRestClient.get_task_logs()
MCP Tool: get_test_results_detailed → fetch_evergreen_task_test_results() → EvergreenRestClient.get_task_test_results()
MCP Tool: download_task_artifacts_evergreen → fetch_task_artifacts() → EvergreenRestClient.get_task_details()
```

---

## Architectural Context

- **Module**: `evergreen_mcp` — An MCP (Model Context Protocol) server providing tools for the Evergreen CI/CD platform
- **Dependencies**:
  - `gql` + `gql.transport.aiohttp` — GraphQL client library
  - `fastmcp` — MCP server framework
  - `aiohttp` — REST client HTTP transport
  - `httpx` — Artifact download HTTP transport
  - `pydantic` — Data models for REST responses only
  - `sentry_sdk` — Error reporting
  - `yaml` — Config file parsing
- **Configuration**:
  - `~/.evergreen.yml` — User credentials and `projects_for_directory` mapping
  - Environment variables: `EVERGREEN_USER`, `EVERGREEN_API_KEY`, `EVERGREEN_PROJECT`, `WORKSPACE_PATH`, `EVERGREEN_URI`, `EVERGREEN_AUTH_MODE`, `EVERGREEN_OIDC_GRAPHQL_URL`, `EVERGREEN_OIDC_REST_URL`, `EVERGREEN_API_KEY_GRAPHQL_URL`, `EVERGREEN_API_KEY_REST_URL`, `EVERGREEN_MCP_TRANSPORT`, `EVERGREEN_MCP_HOST`, `EVERGREEN_MCP_PORT`, `SENTRY_DSN`, `SENTRY_ENABLED`
  - CLI args: `--project-id`, `--workspace-dir`, `--transport`, `--host`, `--port`
- **Authentication**: Three modes — OIDC (bearer token with auto-refresh), API key (user+key headers), per-request (no default client; bearer_token passed per tool call)
- **Related Tests**:
  - `tests/test_failed_jobs_tools.py` — Mocks `AsyncMock` for GraphQL client; tests field extraction from `get_patch_failed_tasks`, `get_task_logs`, `get_task_test_results` return shapes
  - `tests/test_project_inference.py` — Mocks GraphQL client for `get_inferred_project_ids`; tests aggregation and confidence logic
  - `tests/test_mcp_client.py` — Integration test (skipped by default); no direct GraphQL assertions
  - `tests/test_evergreen_rest_client.py` — REST client tests only; no GraphQL
  - `tests/test_artifact_download_tools.py` — REST-only; no GraphQL

---

## Summary

The codebase defines **11 GraphQL query constants** in `evergreen_queries.py`, but only **9 are imported** by the client and **7 are actually consumed** by the MCP tool/resource layer:

| Query Constant | Imported | Has Client Method | Consumed by Tool/Resource | Notes |
|---|---|---|---|---|
| `GET_PROJECTS` | Yes | `get_projects()` | `evergreen://projects` resource | `groupDisplayName` requested but discarded; `branch` discarded by resource |
| `GET_PROJECT` | Yes | `get_project()` | **None** | Fully wired but unused |
| `GET_PROJECT_SETTINGS` | Yes | `get_project_settings()` | **None** | Fully wired but unused |
| `GET_PROJECT_PATCHES` | **No** | **None** | **None** | Dead code — never imported |
| `GET_PROJECT_BUILDS` | **No** | **None** | **None** | Dead code — incomplete query (has TODO comment) |
| `GET_USER_RECENT_PATCHES` | Yes | `get_user_recent_patches()` | `list_user_recent_patches_evergreen` | All fields consumed |
| `GET_PATCH_FAILED_TASKS` | Yes | `get_patch_failed_tasks()` | `get_patch_failed_jobs_evergreen` | All fields consumed |
| `GET_VERSION_WITH_FAILED_TASKS` | Yes | `get_version_with_failed_tasks()` | **None** | Client method exists but never called by any tool |
| `GET_TASK_LOGS` | Yes | `get_task_logs()` | `get_task_log_summary` | `id` and `execution` from response not consumed (args used instead); nested `taskLogs.taskId`/`taskLogs.execution` not consumed |
| `GET_TASK_TEST_RESULTS` | Yes | `get_task_test_results()` | `get_test_results_summary` | All fields consumed |
| `GET_INFERRED_PROJECT_IDS` | Yes | `get_inferred_project_ids()` | `get_inferred_project_ids_evergreen` + project inference in other tools | `id` field requested but never consumed by `fetch_inferred_project_ids` |

**Key findings**:
1. **4 queries are dead/unused**: `GET_PROJECT`, `GET_PROJECT_SETTINGS`, `GET_PROJECT_PATCHES`, `GET_PROJECT_BUILDS`. Two are never even imported.
2. `GET_VERSION_WITH_FAILED_TASKS` is imported and has a client method, but is never called by any MCP tool — the patch-based path (`GET_PATCH_FAILED_TASKS`) is used exclusively.
3. Minor field waste: `groupDisplayName` in `GET_PROJECTS`, `id` in `GET_INFERRED_PROJECT_IDS`, and `branch` (via `GET_PROJECTS` in the resource path) are requested but never consumed.
4. The transformation pattern is consistent: the GraphQL client returns raw dicts from the API response, and `failed_jobs_tools.py` applies the transformation (camelCase → snake_case renaming, nesting restructuring, filtering, summary construction).
5. `artifact_download_tools.py` does **not use GraphQL** — it exclusively uses the REST client.
6. `models.py` (Pydantic models) are used **only** by the REST client path, not the GraphQL path. GraphQL results flow as untyped `Dict[str, Any]` throughout.
