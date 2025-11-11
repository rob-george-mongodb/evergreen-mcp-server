"""MCP tool definitions and handlers for Evergreen REST endpoints
"""
import logging
import os
from pathlib import Path
import tarfile
from typing import Dict, Optional
from urllib.parse import urlparse

import httpx

from evergreen_mcp.models import TaskResponse


logger = logging.getLogger(__name__)

def get_api_user(api_user: Optional[str] = None) -> Optional[str]:
    """Get the API user from parameter or environment variable.

    Args:
        api_user: Optional API user parameter

    Returns:
        API user string or None if not provided
    """
    if api_user:
        return api_user

    #TODO - change to be compatible w the offical MCP  convention
    return os.environ.get("EVERGREEN_API_USER")


def download_task_artifacts(
    task_id: str,
    artifact_filter: Optional[str] = None,
    work_dir: str = "WORK",
    api_user: Optional[str] = None,
) -> Dict[str, Path]:
    """Download artifacts for a task from Evergreen API

    Args:
        task_id: The ID of the task to download artifacts for
        artifact_filter: Optional filter to download only artifacts containing this string (default: None for all)
        work_dir: The base directory to create artifact folders in (default: "WORK")
        api_user: The username for Evergreen API (optional, defaults to EVERGREEN_API_USER env var)

    Returns:
        Dictionary mapping artifact names to their download paths

    Raises:
        ValueError: If API key is missing or no artifacts found
        HTTPError: If the API request fails
        Exception: For other errors (e.g., file extraction)
    """
    logger.info(f"Downloading artifacts for task: {task_id}")

    # Get the task details to find artifacts
    task = get_task_details(task_id, api_user=api_user)

    if not task.artifacts:
        logger.warning(f"No artifacts found for task: {task_id}")
        return {}

    # Filter artifacts if specified
    artifacts_to_download = task.artifacts
    if artifact_filter:
        artifacts_to_download = [
            artifact
            for artifact in task.artifacts
            if artifact_filter.lower() in artifact.name.lower()
        ]
        logger.info(
            f"Filtered to {len(artifacts_to_download)} artifacts containing '{artifact_filter}'"
        )

    if not artifacts_to_download:
        logger.warning(
            f"No artifacts match filter '{artifact_filter}' for task: {task_id}"
        )
        # Provide helpful error message with all available artifacts
        artifact_names = [a.name for a in task.artifacts]

        error_msg = f"No artifacts match filter '{artifact_filter}'.\n\n"
        error_msg += f"Available artifacts ({len(artifact_names)} total):\n"
        # List ALL artifacts, not truncated
        for name in artifact_names:
            error_msg += f"  - {name}\n"

        raise ValueError(error_msg)

    # Create directory structure with version_id as parent to group all tasks from same patch
    version_dir = Path(work_dir) / task.version_id
    task_dir_name = f"task-{task.display_name}-{task.execution}"
    artifacts_dir = version_dir / task_dir_name
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Created artifacts directory: {artifacts_dir}")

    # Get API key for downloading
    evergreen_api_key = os.environ.get("EVERGREEN_API_KEY")
    if not evergreen_api_key:
        raise ValueError("EVERGREEN_API_KEY environment variable not set")

    downloaded_artifacts = {}

    # Download each artifact
    for artifact in artifacts_to_download:
        if artifact.ignore_for_fetch:
            logger.info(f"Skipping artifact '{artifact.name}' (marked to ignore)")
            continue

        logger.info(f"Downloading artifact: {artifact.name}")

        try:
            # Extract filename from URL, handling query parameters
            parsed_url = urlparse(artifact.url)
            file_name = Path(parsed_url.path).name
            if not file_name:
                # Fallback to artifact name if no filename in URL
                file_name = artifact.name.replace(" ", "_").replace("/", "_")
                # Add extension based on content type
                if artifact.content_type == "application/x-gzip":
                    file_name += ".tgz"
                elif artifact.content_type == "text/html":
                    file_name += ".html"

            file_path = artifacts_dir / file_name

            # Download the artifact
            headers = {"Api-Key": evergreen_api_key}
            user = get_api_user(api_user)
            if user:
                headers["Api-User"] = user
            with httpx.Client(timeout=60) as client:
                response = client.get(artifact.url, headers=headers)
                response.raise_for_status()

                # Save the downloaded file
                with open(file_path, "wb") as f:
                    f.write(response.content)

                logger.info(f"Downloaded: {file_path}")

                # Extract compressed files
                if artifact.content_type == "application/x-gzip" or file_name.endswith(
                    (".tar.gz", ".tgz")
                ):
                    logger.info(f"Extracting compressed archive: {file_path}")
                    try:
                        with tarfile.open(file_path, "r:gz") as tar:
                            tar.extractall(path=artifacts_dir)
                        logger.info(f"Extracted archive to: {artifacts_dir}")
                    except Exception as e:
                        logger.warning(f"Failed to extract {file_path}: {e}")

                downloaded_artifacts[artifact.name] = file_path

        except Exception as e:
            logger.error(f"Failed to download artifact '{artifact.name}': {e}")
            continue

    logger.info(f"Downloaded {len(downloaded_artifacts)} artifacts to: {artifacts_dir}")
    return downloaded_artifacts

def get_task_details(
    task_id: str, fetch_all_executions: bool = False, api_user: Optional[str] = None
) -> TaskResponse:
    """Fetch detailed information about a specific task from the Evergreen API

    Args:
        task_id: The ID of the task to fetch details for
        fetch_all_executions: Whether to fetch info about all executions of this task (default: False)
        api_user: The username for Evergreen API (optional, defaults to EVERGREEN_API_USER env var)

    Returns:
        TaskResponse object representing the requested task

    Raises:
        ValueError: If API key is missing
        HTTPError: If the API request fails
    """
    # API endpoint for getting a specific task by ID
    api_url = f"https://evergreen.mongodb.com/rest/v2/tasks/{task_id}"

    # Get API key from environment
    evergreen_api_key = os.environ.get("EVERGREEN_API_KEY")
    if not evergreen_api_key:
        raise ValueError("EVERGREEN_API_KEY environment variable not set")

    # Get API user
    api_user = get_api_user(api_user)

    # Set up headers and params
    headers = {"Api-Key": evergreen_api_key}
    if api_user:
        headers["Api-User"] = api_user
    params = {}

    # Add fetch_all_executions parameter if requested
    if fetch_all_executions:
        params["fetch_all_executions"] = "true"

    try:
        with httpx.Client(timeout=30) as client:
            response = client.get(api_url, headers=headers, params=params)
            response.raise_for_status()
            task_data = response.json()
    except httpx.HTTPError as e:
        raise httpx.HTTPError(f"Failed to retrieve task from Evergreen API: {e}")

    # Parse the response into our Pydantic model
    task = TaskResponse.model_validate(task_data)
    return task