"""Tests for restart_cli module."""

import json
import subprocess
from io import StringIO
from unittest import mock

import pytest

from evergreen_waterfall_triage.restart_cli import (
    CLIError,
    TaskRestart,
    extract_task_id_from_url,
    get_oauth_token,
    main,
    parse_request,
    parse_task_restarts_from_stdin,
)


@pytest.fixture
def aiohttp_client_mock():
    """Create a mock aiohttp ClientSession with proper async context manager support."""
    from unittest.mock import AsyncMock, MagicMock

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text = AsyncMock(return_value="OK")

    mock_post_context = AsyncMock()
    mock_post_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_post_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_post_context)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with mock.patch("aiohttp.ClientSession", return_value=mock_session):
        yield mock_session


def test_extract_task_id_from_url():
    """Test extracting task_id from various URL formats."""
    url = "https://evergreen.mongodb.com/task/task_abc123"
    assert extract_task_id_from_url(url) == "task_abc123"

    url_with_slash = "https://evergreen.mongodb.com/task/task_abc123/"
    assert extract_task_id_from_url(url_with_slash) == "task_abc123"

    corp_url = "https://evergreen.corp.mongodb.com/task/another_task_id"
    assert extract_task_id_from_url(corp_url) == "another_task_id"


def test_extract_task_id_from_url_invalid():
    """Test that invalid URLs raise CLIError."""
    with pytest.raises(CLIError, match="Invalid task URL format"):
        extract_task_id_from_url("https://evergreen.mongodb.com/not-a-task/abc123")

    with pytest.raises(CLIError, match="Invalid task URL format"):
        extract_task_id_from_url("not-a-url")


def test_parse_request_defaults():
    """Test parsing request with default values."""
    request = parse_request([])
    assert request.dry_run is False
    assert request.base_url == "https://evergreen.corp.mongodb.com/rest/v2"


def test_parse_request_dry_run():
    """Test parsing request with dry run flag."""
    request = parse_request(["--dryRun"])
    assert request.dry_run is True


def test_parse_request_custom_base_url():
    """Test parsing request with custom base URL."""
    request = parse_request(["--baseUrl", "https://custom.example.com/api"])
    assert request.base_url == "https://custom.example.com/api"


def test_parse_task_restarts_from_stdin_streaks_format():
    """Test parsing valid streaks format input."""
    input_data = """{
  "streaks": [
    {
      "variant": "ACWorkloadManagement",
      "task_name": "TestTask",
      "consecutive_failure_count": 2,
      "latest_failure": {
        "task_id": "task_123",
        "task_url": "https://evergreen.mongodb.com/task/task_123"
      }
    },
    {
      "variant": "ACWorkloadManagement",
      "task_name": "AnotherTask",
      "consecutive_failure_count": 1,
      "latest_failure": {
        "task_id": "task_789"
      }
    }
  ]
}"""

    with mock.patch("sys.stdin", StringIO(input_data)):
        restarts = parse_task_restarts_from_stdin()

    assert len(restarts) == 2
    assert restarts[0].task_name == "TestTask"
    assert restarts[0].task_id == "task_123"
    assert restarts[0].variant == "ACWorkloadManagement"
    assert restarts[0].consecutive_failure_count == 2
    assert restarts[1].task_name == "AnotherTask"
    assert restarts[1].task_id == "task_789"


def test_parse_task_restarts_from_stdin_empty():
    """Test that empty input returns empty list."""
    input_data = ""

    with mock.patch("sys.stdin", StringIO(input_data)):
        restarts = parse_task_restarts_from_stdin()

    assert len(restarts) == 0


def test_parse_task_restarts_from_stdin_invalid_json():
    """Test that invalid JSON raises CLIError."""
    input_data = "not valid json"

    with mock.patch("sys.stdin", StringIO(input_data)):
        with pytest.raises(CLIError, match="Invalid JSON"):
            parse_task_restarts_from_stdin()


def test_parse_task_restarts_from_stdin_missing_streaks():
    """Test that missing streaks array raises CLIError."""
    input_data = '{"variant": "ACWorkloadManagement"}'

    with mock.patch("sys.stdin", StringIO(input_data)):
        with pytest.raises(CLIError, match="must contain 'streaks' array"):
            parse_task_restarts_from_stdin()


def test_parse_task_restarts_from_stdin_missing_field():
    """Test that missing required fields in streaks raise CLIError."""
    input_data = '{"streaks": [{"variant": "ACWorkloadManagement"}]}'

    with mock.patch("sys.stdin", StringIO(input_data)):
        with pytest.raises(CLIError, match="Missing required field"):
            parse_task_restarts_from_stdin()


def test_parse_task_restarts_from_stdin_missing_task_id():
    """Test that missing task_id and task_url in latest_failure raises CLIError."""
    input_data = '{"streaks": [{"task_name": "Test", "latest_failure": {}}]}'

    with mock.patch("sys.stdin", StringIO(input_data)):
        with pytest.raises(CLIError, match="Missing task_id in latest_failure"):
            parse_task_restarts_from_stdin()


def test_get_oauth_token_success():
    """Test successful OAuth token retrieval."""
    mock_result = mock.Mock()
    mock_result.stdout = "test-token-123\n"
    mock_result.stderr = ""

    with mock.patch("subprocess.run", return_value=mock_result):
        token = get_oauth_token()

    assert token == "test-token-123"


def test_get_oauth_token_not_found():
    """Test that missing evergreen CLI raises CLIError."""
    with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
        with pytest.raises(CLIError, match="evergreen CLI not found"):
            get_oauth_token()


def test_get_oauth_token_failure():
    """Test that failed token retrieval raises CLIError."""
    error = subprocess.CalledProcessError(1, "cmd", stderr="authentication failed")

    with mock.patch("subprocess.run", side_effect=error):
        with pytest.raises(CLIError, match="failed"):
            get_oauth_token()


def test_get_oauth_token_empty():
    """Test that empty token raises CLIError."""
    mock_result = mock.Mock()
    mock_result.stdout = "\n"
    mock_result.stderr = ""

    with mock.patch("subprocess.run", return_value=mock_result):
        with pytest.raises(CLIError, match="returned empty token"):
            get_oauth_token()


def test_main_dry_run():
    """Test main function with dry run mode."""
    input_data = '{"streaks": [{"variant": "ACWorkloadManagement", "task_name": "TestTask", "consecutive_failure_count": 1, "latest_failure": {"task_id": "task_123"}}]}'

    with mock.patch("sys.stdin", StringIO(input_data)):
        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            exit_code = main(["--dryRun"])

    assert exit_code == 0
    output = json.loads(mock_stdout.getvalue())
    assert output["summary"]["total"] == 1
    assert output["summary"]["success"] == 1
    assert output["tasks"][0]["dry_run"] is True


@pytest.mark.asyncio
async def test_restart_task_success(aiohttp_client_mock):
    """Test successful task restart."""
    from evergreen_waterfall_triage.restart_cli import restart_task

    task = TaskRestart(
        task_name="TestTask",
        task_id="task_123",
        variant="ACWorkloadManagement",
        consecutive_failure_count=1,
    )

    mock_response = aiohttp_client_mock.post.return_value.__aenter__.return_value
    mock_response.status = 200
    mock_response.text = mock.AsyncMock(return_value="OK")

    result = await restart_task(
        task=task,
        token="test-token",
        base_url="https://evergreen.corp.mongodb.com/rest/v2",
        dry_run=False,
    )

    assert result["success"] is True
    assert "error" not in result


@pytest.mark.asyncio
async def test_restart_task_failure(aiohttp_client_mock):
    """Test failed task restart."""
    from evergreen_waterfall_triage.restart_cli import restart_task

    task = TaskRestart(
        task_name="TestTask",
        task_id="task_123",
        variant="ACWorkloadManagement",
        consecutive_failure_count=1,
    )

    mock_response = aiohttp_client_mock.post.return_value.__aenter__.return_value
    mock_response.status = 404
    mock_response.text = mock.AsyncMock(return_value="Task not found")

    result = await restart_task(
        task=task,
        token="test-token",
        base_url="https://evergreen.corp.mongodb.com/rest/v2",
        dry_run=False,
    )

    assert result["success"] is False
    assert "HTTP 404" in result["error"]
