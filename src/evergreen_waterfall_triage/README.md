# Evergreen Waterfall Investigation Tools

This package exposes four local CLIs:

- `evergreen-waterfall-triage` to find open task failure streaks
- `evergreen-waterfall-investigate` to launch and clean up per-failure investigations
- `evergreen-restart-tasks` to restart failed Evergreen tasks in bulk
- `evergreen-waterfall-download-artifacts` to download artifacts from failed tasks

`evergreen-waterfall-triage` finds open task failure streaks on the Evergreen waterfall.

It answers one question: which task on which variant is still failing, and for how long?

## Rules

- Scope: current streaks only
- Key: `variant + task_name`
- `failed` increments the streak
- `success` ends the streak
- every other status is neutral
- task absence is neutral
- versions without `startTime`, `finishTime`, or tasks are ignored

The CLI is intentionally strict. If Evergreen truncates the task list for a version, it exits with an error instead of guessing.

## Auth

It uses the same Evergreen credentials as the rest of the repo:

- `EVERGREEN_USER` and `EVERGREEN_API_KEY`, or
- OIDC via `evergreen login`

## Usage

```bash
evergreen-waterfall-triage \
  --projectIdentifier mms \
  --variant enterprise-rhel-80-64-bit \
  --variant ubuntu2204-debug \
  --minNumConsecutiveFailures 2
```

Use `--waterfallLimit` to widen the history window.

## Investigation Launcher

`evergreen-waterfall-investigate` consumes the triage JSON and launches one
investigation per open streak.

It creates a git worktree in a target repository and runs `opencode` there.

### Examples

Two-step flow:

```bash
evergreen-waterfall-triage \
  --projectIdentifier mms-v20260506 \
  --variants "ACWorkloadManagement,Backup" \
  --waterfallLimit 300 \
  > qaFailures.json

evergreen-waterfall-investigate \
  --triageJson qaFailures.json \
  --targetRepoPath ~/git/mms \
  --jobs 4
```

Single-step flow:

```bash
evergreen-waterfall-investigate \
  --projectIdentifier mms-v20260506 \
  --variants "ACWorkloadManagement,Backup" \
  --waterfallLimit 300 \
  --targetRepoPath ~/git/mms \
  --jobs 4
```

Use `--dryRun` to preview worktree paths and `opencode` commands without
executing them.

`opencode` execution modes:

- default `--opencodeMode auto`: try the attached server first when
  `--opencodeAttachUrl` is provided, then fall back to local CLI mode if the
  failure looks like session creation failed
- `--opencodeMode attach`: always use `opencode run --attach <url> --dir <worktree>`
- `--opencodeMode local`: always use local `opencode run --dir <worktree>`

Attach example:

```bash
evergreen-waterfall-investigate launch \
  --triageJson qaFailures.json \
  --targetRepoPath ~/git/mms \
  --opencodeMode attach \
  --opencodeAttachUrl http://localhost:4096
```

In attach mode, `--dir` must be a path the running `opencode` server can see on
its own host.

The checked-in `qaFailures.json` file in this repo is valid input for this
command.

## Cleanup

Use the `cleanup` subcommand to remove investigation worktrees created by this
tool.

Dry run:

```bash
evergreen-waterfall-investigate cleanup \
  --targetRepoPath ~/git/mms \
  --dryRun
```

Remove worktrees and their generated branches:

```bash
evergreen-waterfall-investigate cleanup \
  --targetRepoPath ~/git/mms \
  --removeBranches
```

Cleanup only considers worktrees that are both:

- under the configured investigation worktree root
- on branches beginning with `ai/evergreen/`

## Output

The command writes JSON to `stdout`.

- `query`: the exact inputs
- `summary`: version counts and streak counts
- `streaks`: one object per open task streak

Each streak includes:

- `variant`
- `task_name`
- `consecutive_failure_count`
- `is_truncated_by_waterfall_limit`
- `latest_failure`
- `oldest_failure_in_window`
- `boundary`
- `failures`

Each failure occurrence includes a direct Spruce task URL.

## Task Restart Tool

`evergreen-restart-tasks` reads JSON input (one object per line) from stdin and
restarts the "latest" task for each entry using the Evergreen REST API.

### Input Format

Expects full JSON object with `streaks` array from waterfall triage output. Extracts `latest_failure.task_id` from each streak:

```bash
evergreen-waterfall-triage \
  --projectIdentifier mms \
  --variant ACWorkloadManagement \
  | evergreen-restart-tasks
```

The `latest_failure` object in each streak must contain either:
- `task_id` field (used directly)
- `task_url` field (task_id is extracted from the URL)

### Authentication

Uses `evergreen client get-oauth-token` to obtain an OAuth bearer token for
authentication.

### Usage

Restart tasks from triage output:

```bash
evergreen-waterfall-triage \
  --projectIdentifier mms \
  --variant ACWorkloadManagement \
  | evergreen-restart-tasks
```

Dry run (preview without executing):

```bash
cat qaFailures.json | evergreen-restart-tasks --dryRun
```

Custom API endpoint:

```bash
cat qaFailures.json | evergreen-restart-tasks --baseUrl https://evergreen.mongodb.com/rest/v2
```

### Output

Writes JSON to stdout with results for each task:

```json
{
  "tasks": [
    {
      "task_name": "E2E_NDS_LOCAL_DB_Security_Connection_7_0",
      "task_id": "task_abc123",
      "variant": "ACWorkloadManagement",
      "consecutive_failure_count": 2,
      "success": true
    }
  ],
  "summary": {
    "total": 1,
    "success": 1,
    "failed": 0
  }
}
```

Returns exit code 0 if all tasks succeeded, 1 if any failed.

## Artifact Download Tool

`evergreen-waterfall-download-artifacts` downloads artifacts from failed tasks identified in waterfall triage output.

### Purpose

This tool extracts task IDs from the `streaks[].latest_failure.task_id` field in triage JSON and uses the `evergreen fetch artifacts` CLI to download them to a user-specified directory.

### Usage

Download all artifacts from failed tasks:

```bash
evergreen-waterfall-triage \
  --projectIdentifier mms \
  --variant ACWorkloadManagement \
  | evergreen-waterfall-download-artifacts \
    --artifactDownloadDir ./artifacts
```

Download specific artifacts only:

```bash
cat qaFailures.json | evergreen-waterfall-download-artifacts \
  --artifactDownloadDir ./artifacts \
  --artifact_name logs \
  --artifact_name results
```

Use `--shallow` to skip downloading artifacts from dependency tasks:

```bash
cat qaFailures.json | evergreen-waterfall-download-artifacts \
  --artifactDownloadDir ./artifacts \
  --shallow
```

Read from a file instead of stdin:

```bash
evergreen-waterfall-download-artifacts \
  --triageJson qaFailures.json \
  --artifactDownloadDir ./artifacts
```

### Arguments

- `--artifactDownloadDir` (required): Directory where artifacts will be downloaded. Each task's artifacts will be placed in a subdirectory named after the task ID.
- `--triageJson`: Path to triage JSON file. If not provided, reads from stdin.
- `--artifact_name`: Specific artifact name to download (can be specified multiple times). If not provided, downloads all artifacts for each task.
- `--shallow`: Don't recursively download artifacts from dependency tasks.

### Directory Structure

Artifacts are organized by task ID:

```
<artifactDownloadDir>/
├── task_id_1/
│   ├── artifact1.tgz
│   ├── artifact2.log
│   └── ...
├── task_id_2/
│   ├── artifact1.tgz
│   └── ...
└── ...
```

### Output

Writes JSON to stdout with download results:

```json
{
  "success": true,
  "message": "Downloaded artifacts for 11/11 tasks",
  "task_count": 11,
  "success_count": 11,
  "download_dir": "/path/to/artifacts",
  "results": [
    {
      "task_id": "task_abc123",
      "success": true,
      "download_dir": "/path/to/artifacts/task_abc123"
    }
  ]
}
```

Returns exit code 0 if all downloads succeeded, 1 if any failed.

### Requirements

- The `evergreen` CLI must be installed and authenticated (`evergreen login`)
- Network access to Evergreen artifact storage
