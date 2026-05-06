"""CLI for downloading artifacts from failed tasks in waterfall triage output."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


class CLIError(Exception):
    """User-facing CLI validation error."""

    def __init__(self, message: str, exit_code: int = 2):
        super().__init__(message)
        self.exit_code = exit_code


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CLIError(message)


@dataclass(frozen=True)
class ArtifactDownloadRequest:
    triage_json_path: Optional[str]
    artifact_download_dir: str
    artifact_names: List[str]
    shallow: bool


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog="evergreen-waterfall-download-artifacts",
        description="Download artifacts from failed tasks in waterfall triage output",
    )
    parser.add_argument(
        "--triageJson",
        help="Path to triage JSON file. If not provided, reads from stdin.",
    )
    parser.add_argument(
        "--artifactDownloadDir",
        required=True,
        help="Directory to download artifacts into. Artifacts will be organized by task_id.",
    )
    parser.add_argument(
        "--artifact_name",
        action="append",
        default=[],
        help="Specific artifact name to download (can be specified multiple times). "
        "If not provided, downloads all artifacts.",
    )
    parser.add_argument(
        "--shallow",
        action="store_true",
        help="Don't recursively download artifacts from dependency tasks.",
    )
    return parser


def parse_request(argv: Sequence[str] | None = None) -> ArtifactDownloadRequest:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.artifactDownloadDir:
        raise CLIError("--artifactDownloadDir is required")

    return ArtifactDownloadRequest(
        triage_json_path=args.triageJson,
        artifact_download_dir=args.artifactDownloadDir,
        artifact_names=args.artifact_name,
        shallow=args.shallow,
    )


def extract_task_ids(triage_data: Dict[str, Any]) -> List[str]:
    """Extract task IDs from streaks[].latest_failure.task_id in triage output.
    
    Args:
        triage_data: Parsed JSON from waterfall triage output
        
    Returns:
        List of unique task IDs from failed tasks
        
    Raises:
        CLIError: If streaks not found or invalid structure
    """
    if "streaks" not in triage_data:
        raise CLIError("Invalid triage JSON: 'streaks' key not found")
    
    streaks = triage_data["streaks"]
    if not isinstance(streaks, list):
        raise CLIError("Invalid triage JSON: 'streaks' must be a list")
    
    task_ids = []
    for idx, streak in enumerate(streaks):
        if not isinstance(streak, dict):
            raise CLIError(f"Invalid triage JSON: streak {idx} is not a dict")
        
        if "latest_failure" not in streak:
            raise CLIError(f"Invalid triage JSON: streak {idx} missing 'latest_failure'")
        
        latest_failure = streak["latest_failure"]
        if not isinstance(latest_failure, dict):
            raise CLIError(
                f"Invalid triage JSON: streak {idx} 'latest_failure' is not a dict"
            )
        
        if "task_id" not in latest_failure:
            raise CLIError(
                f"Invalid triage JSON: streak {idx} 'latest_failure' missing 'task_id'"
            )
        
        task_id = latest_failure["task_id"]
        if not isinstance(task_id, str):
            raise CLIError(
                f"Invalid triage JSON: streak {idx} 'task_id' is not a string"
            )
        
        if task_id not in task_ids:
            task_ids.append(task_id)
    
    return task_ids


def download_artifacts_for_task(
    task_id: str,
    download_dir: Path,
    artifact_names: List[str],
    shallow: bool,
) -> Dict[str, Any]:
    """Download artifacts for a single task using evergreen CLI.
    
    Args:
        task_id: The Evergreen task ID
        download_dir: Base directory for downloads
        artifact_names: Specific artifacts to download (empty list = all)
        shallow: Whether to skip dependency artifacts
        
    Returns:
        Dict with task_id, success status, and download location
    """
    task_dir = download_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        "evergreen",
        "fetch",
        "--task", task_id,
        "--dir", str(task_dir),
        "--artifacts",
    ]
    
    if shallow:
        cmd.append("--shallow")
    
    for artifact_name in artifact_names:
        cmd.extend(["--artifact_name", artifact_name])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        return {
            "task_id": task_id,
            "success": True,
            "download_dir": str(task_dir),
            "command": " ".join(cmd),
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.CalledProcessError as e:
        return {
            "task_id": task_id,
            "success": False,
            "download_dir": str(task_dir),
            "command": " ".join(cmd),
            "error": e.stderr or str(e),
            "returncode": e.returncode,
        }
    except Exception as e:
        return {
            "task_id": task_id,
            "success": False,
            "download_dir": str(task_dir),
            "command": " ".join(cmd),
            "error": str(e),
        }


def load_triage_json(request: ArtifactDownloadRequest) -> Dict[str, Any]:
    """Load triage JSON from file or stdin.
    
    Args:
        request: Download request with triage_json_path
        
    Returns:
        Parsed JSON data
        
    Raises:
        CLIError: If file not found or invalid JSON
    """
    try:
        if request.triage_json_path:
            with open(request.triage_json_path, "r") as f:
                return json.load(f)
        else:
            return json.load(sys.stdin)
    except FileNotFoundError as e:
        raise CLIError(f"Triage JSON file not found: {request.triage_json_path}")
    except json.JSONDecodeError as e:
        raise CLIError(f"Invalid JSON in triage file: {e}")


def run_downloads(request: ArtifactDownloadRequest) -> Dict[str, Any]:
    """Main download orchestration.
    
    Args:
        request: Download request with all parameters
        
    Returns:
        Summary dict with results for each task
    """
    triage_data = load_triage_json(request)
    task_ids = extract_task_ids(triage_data)
    
    if not task_ids:
        return {
            "success": True,
            "message": "No failed tasks found in triage output",
            "task_count": 0,
            "results": [],
        }
    
    download_dir = Path(request.artifact_download_dir).resolve()
    download_dir.mkdir(parents=True, exist_ok=True)
    
    results = []
    success_count = 0
    
    for task_id in task_ids:
        result = download_artifacts_for_task(
            task_id=task_id,
            download_dir=download_dir,
            artifact_names=request.artifact_names,
            shallow=request.shallow,
        )
        results.append(result)
        if result["success"]:
            success_count += 1
    
    return {
        "success": success_count == len(task_ids),
        "message": f"Downloaded artifacts for {success_count}/{len(task_ids)} tasks",
        "task_count": len(task_ids),
        "success_count": success_count,
        "download_dir": str(download_dir),
        "results": results,
    }


def main(argv: Sequence[str] | None = None) -> int:
    try:
        request = parse_request(argv)
        result = run_downloads(request)
        
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
        
        return 0 if result["success"] else 1
    except CLIError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())