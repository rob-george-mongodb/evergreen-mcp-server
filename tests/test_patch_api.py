"""Tests for patch_api module."""

from unittest import mock
from unittest.mock import AsyncMock, MagicMock

import pytest

from evergreen_waterfall_triage.patch_api import (
    PatchAddTasksRequest,
    VariantTasks,
    add_tasks_to_patch,
)


@pytest.fixture
def aiohttp_client_mock():
    """Create a mock aiohttp ClientSession with proper async context manager support."""
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text = AsyncMock(return_value="OK")
    mock_response.json = AsyncMock(return_value={"status": "success"})

    mock_post_context = AsyncMock()
    mock_post_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_post_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_post_context)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with mock.patch("aiohttp.ClientSession", return_value=mock_session):
        yield mock_session


@pytest.mark.asyncio
async def test_add_tasks_to_patch_dry_run():
    """Test dry run mode returns expected structure without making API calls."""
    request = PatchAddTasksRequest(
        patch_id="test_patch_123",
        variant_tasks=[
            VariantTasks(variant="variant1", tasks=["task1", "task2"]),
            VariantTasks(variant="variant2", tasks=["task3"]),
        ],
        dry_run=True,
    )

    result = await add_tasks_to_patch(request, token="test_token")

    assert result["patch_id"] == "test_patch_123"
    assert result["summary"]["total"] == 2
    assert result["summary"]["success"] == 2
    assert result["summary"]["failed"] == 0
    assert len(result["variant_tasks"]) == 2
    assert all(vt["dry_run"] is True for vt in result["variant_tasks"])


@pytest.mark.asyncio
async def test_add_tasks_to_patch_success(aiohttp_client_mock):
    """Test successful API call to add tasks."""
    request = PatchAddTasksRequest(
        patch_id="test_patch_123",
        variant_tasks=[
            VariantTasks(variant="variant1", tasks=["task1", "task2"]),
        ],
        dry_run=False,
        base_url="https://test.example.com/rest/v2",
    )

    result = await add_tasks_to_patch(request, token="test_token")

    assert result["patch_id"] == "test_patch_123"
    assert result["summary"]["total"] == 1
    assert result["summary"]["success"] == 1
    assert result["summary"]["failed"] == 0
    assert result["variant_tasks"][0]["success"] is True


@pytest.mark.asyncio
async def test_add_tasks_to_patch_failure(aiohttp_client_mock):
    """Test handling of API failure."""
    request = PatchAddTasksRequest(
        patch_id="test_patch_123",
        variant_tasks=[
            VariantTasks(variant="variant1", tasks=["task1"]),
        ],
        dry_run=False,
        base_url="https://test.example.com/rest/v2",
    )

    mock_response = aiohttp_client_mock.post.return_value.__aenter__.return_value
    mock_response.status = 400
    mock_response.text = AsyncMock(return_value="Invalid variant")

    result = await add_tasks_to_patch(request, token="test_token")

    assert result["summary"]["total"] == 1
    assert result["summary"]["success"] == 0
    assert result["summary"]["failed"] == 1
    assert result["variant_tasks"][0]["success"] is False
    assert "HTTP 400" in result["variant_tasks"][0]["error"]


@pytest.mark.asyncio
async def test_add_tasks_to_patch_multiple_variants(aiohttp_client_mock):
    """Test adding tasks to multiple variants."""
    request = PatchAddTasksRequest(
        patch_id="test_patch_123",
        variant_tasks=[
            VariantTasks(variant="variant1", tasks=["task1", "task2"]),
            VariantTasks(variant="variant2", tasks=["task3"]),
        ],
        dry_run=False,
        base_url="https://test.example.com/rest/v2",
    )

    mock_response = aiohttp_client_mock.post.return_value.__aenter__.return_value
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"status": "success"})

    result = await add_tasks_to_patch(request, token="test_token")

    assert result["summary"]["total"] == 2
    assert result["summary"]["success"] == 2
    assert all(vt["success"] for vt in result["variant_tasks"])
