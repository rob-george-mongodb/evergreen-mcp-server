# Evergreen Patch Task Addition Tool

This tool allows adding tasks to an existing Evergreen patch from waterfall triage output.

## Overview

The tool provides two components:

1. **Low-level API** (`patch_api.py`): Direct REST API wrapper for adding tasks to a patch
2. **CLI tool** (`patch_cli.py`): User-facing command-line interface that processes waterfall triage JSON

## Usage

### CLI Usage

```bash
# Add tasks to a patch from waterfall triage output (dry run)
cat waterfall_triage_output.json | evergreen-add-patch-tasks --patchId <patch_id> --dryRun

# Actually add tasks to a patch
cat waterfall_triage_output.json | evergreen-add-patch-tasks --patchId <patch_id>
```

### How It Works

1. Reads JSON from stdin containing waterfall triage output with `streaks` array
2. Extracts tasks from each streak
3. Filters out failures where the actual variant ends with `_generated`
4. Groups tasks by their actual variant (using `the_actual_variant_we_should_stop_using_the_incomprehensible_display_name_ones` field)
5. Calls the Evergreen REST API to add each variant's tasks to the patch

### Input Format

The tool expects JSON with a `streaks` array from the waterfall triage tool:

```json
{
  "streaks": [
    {
      "task_name": "E2E_NDS_Some_Task",
      "latest_failure": {
        "the_actual_variant_we_should_stop_using_the_incomprehensible_display_name_ones": "variant_name",
        "task_id": "...",
        ...
      },
      ...
    }
  ]
}
```

### Output Format

The tool outputs JSON with results:

```json
{
  "patch_id": "...",
  "variant_tasks": [
    {
      "variant": "variant_name",
      "tasks": ["task1", "task2"],
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

### Filtering Generated Variants

Variants ending with `_generated` are automatically filtered out. For example:
- `e2e_nds_autoscaling_generated` → **filtered out**
- `e2e_nds_local_autoscaling` → **included**

### API Usage

```python
from evergreen_waterfall_triage.patch_api import (
    PatchAddTasksRequest,
    VariantTasks,
    add_tasks_to_patch,
)

# Create request
request = PatchAddTasksRequest(
    patch_id="your_patch_id",
    variant_tasks=[
        VariantTasks(variant="variant1", tasks=["task1", "task2"]),
        VariantTasks(variant="variant2", tasks=["task3"]),
    ],
    dry_run=False,
)

# Execute
result = await add_tasks_to_patch(request, token="your_oauth_token")
```

## Example

Using the provided example file:

```bash
# Dry run to see what would be added
cat qaFailures050626_now_with_real_variants.json | evergreen-add-patch-tasks --patchId your_patch_id --dryRun

# This will output:
{
  "patch_id": "your_patch_id",
  "variant_tasks": [
    {
      "variant": "e2e_nds_local_autoscaling",
      "tasks": [
        "E2E_NDS_Compute_Auto_Scaling_Ensure_Uptime_AZURE",
        "E2E_NDS_Low_CPU_Compute_Auto_Scaling_With_Scale_Down_Prohibited_Azure"
      ],
      "dry_run": true
    },
    ...
  ],
  "summary": {"total": 5, "success": 5, "failed": 0}
}
```

## Requirements

- Evergreen CLI installed and configured with OAuth token
- Valid Evergreen credentials with patch modification permissions
- Python 3.10+ with aiohttp installed