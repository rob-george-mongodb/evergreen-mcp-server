"""Tests for add_variant_tasks_cli module."""

import json
import subprocess
from io import StringIO
from unittest import mock

import pytest

from evergreen_waterfall_triage.add_variant_tasks_cli import (
    CLIError,
    CLIRequest,
    build_parser,
    get_oauth_token,
    main,
    parse_request,
)


def test_build_parser():
    """Test parser has required arguments."""
    parser = build_parser()
    assert parser.prog == "evergreen-add-variant-tasks"


def test_parse_request():
    """Test parsing CLI arguments."""
    request = parse_request(
        ["--patchId", "test123", "--variant", "my_variant", "task1", "task2", "task3"]
    )
    assert request.patch_id == "test123"
    assert request.variant == "my_variant"
    assert list(request.tasks) == ["task1", "task2", "task3"]
    assert request.dry_run is False
    assert request.base_url == "https://evergreen.corp.mongodb.com/rest/v2"


def test_parse_request_with_dry_run():
    """Test parsing CLI arguments with dry run."""
    request = parse_request(
        ["--patchId", "test123", "--variant", "my_variant", "--dryRun", "task1"]
    )
    assert request.dry_run is True


def test_parse_request_custom_base_url():
    """Test custom base URL."""
    request = parse_request(
        [
            "--patchId",
            "test123",
            "--variant",
            "my_variant",
            "--baseUrl",
            "https://custom.example.com/rest/v2/",
            "task1",
        ]
    )
    assert request.base_url == "https://custom.example.com/rest/v2"


def test_parse_request_missing_patch_id():
    """Test that missing patchId raises CLIError."""
    with pytest.raises(CLIError):
        parse_request(["--variant", "my_variant", "task1"])


def test_parse_request_missing_variant():
    """Test that missing variant raises CLIError."""
    with pytest.raises(CLIError):
        parse_request(["--patchId", "test123", "task1"])


def test_parse_request_missing_tasks():
    """Test that missing tasks raises CLIError."""
    with pytest.raises(CLIError):
        parse_request(["--patchId", "test123", "--variant", "my_variant"])


def test_get_oauth_token():
    """Test getting OAuth token from evergreen CLI."""
    mock_result = mock.Mock()
    mock_result.stdout = "test_token_123\n"
    mock_result.stderr = ""

    with mock.patch("subprocess.run", return_value=mock_result):
        token = get_oauth_token()
        assert token == "test_token_123"


def test_get_oauth_token_empty():
    """Test empty token raises CLIError."""
    mock_result = mock.Mock()
    mock_result.stdout = "\n"
    mock_result.stderr = ""

    with mock.patch("subprocess.run", return_value=mock_result):
        with pytest.raises(CLIError, match="empty token"):
            get_oauth_token()


def test_get_oauth_token_not_found():
    """Test missing evergreen CLI raises CLIError."""
    with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
        with pytest.raises(CLIError, match="evergreen CLI not found"):
            get_oauth_token()


def test_get_oauth_token_failure():
    """Test evergreen CLI failure raises CLIError."""
    error = subprocess.CalledProcessError(1, "cmd", stderr="error message")
    with mock.patch("subprocess.run", side_effect=error):
        with pytest.raises(CLIError, match="failed"):
            get_oauth_token()


def test_main_dry_run():
    """Test main with dry run mode."""
    with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
        exit_code = main(
            [
                "--patchId",
                "test123",
                "--variant",
                "my_variant",
                "--dryRun",
                "task1",
                "task2",
            ]
        )

    assert exit_code == 0
    output = json.loads(mock_stdout.getvalue())
    assert output["patch_id"] == "test123"
    assert output["summary"]["total"] == 1
    assert output["summary"]["success"] == 1
    assert len(output["variant_tasks"]) == 1
    assert output["variant_tasks"][0]["variant"] == "my_variant"
    assert output["variant_tasks"][0]["tasks"] == ["task1", "task2"]
    assert output["variant_tasks"][0]["dry_run"] is True
    """Test main with failed API call."""
    from unittest.mock import AsyncMock, MagicMock

    mock_response = AsyncMock()
    mock_response.status = 400
    mock_response.text = AsyncMock(return_value="Invalid variant")

    mock_post_context = AsyncMock()
    mock_post_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_post_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_post_context)

    mock_result = mock.Mock()
    mock_result.stdout = "test_token\n"
    mock_result.stderr = ""

    with mock.patch("aiohttp.ClientSession", return_value=mock_session):
        with mock.patch("subprocess.run", return_value=mock_result):
            with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                exit_code = main([
                    "--patchId", "test123",
                    "--variant", "my_variant",
                    "task1"
                ])

    assert exit_code == 1
    output = json.loads(mock_stdout.getvalue())
    assert output["summary"]["success"] == 0
    assert output["summary"]["failed"] == 1
