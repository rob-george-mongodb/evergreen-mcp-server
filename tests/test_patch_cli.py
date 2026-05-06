"""Tests for patch_cli module."""

import json
import subprocess
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from evergreen_waterfall_triage.patch_cli import (
    CLIError,
    CLIRequest,
    _parse_streaks_format,
    build_parser,
    get_oauth_token,
    main,
    parse_request,
    parse_waterfall_triage_from_stdin,
)


def test_build_parser():
    """Test parser has required arguments."""
    parser = build_parser()
    assert parser.prog == "evergreen-add-patch-tasks"


def test_parse_request():
    """Test parsing CLI arguments."""
    request = parse_request(["--patchId", "test123", "--dryRun"])
    assert request.patch_id == "test123"
    assert request.dry_run is True
    assert request.base_url == "https://evergreen.corp.mongodb.com/rest/v2"


def test_parse_request_missing_patch_id():
    """Test that missing patchId raises CLIError."""
    with pytest.raises(CLIError):
        parse_request([])


def test_parse_request_custom_base_url():
    """Test custom base URL."""
    request = parse_request(
        ["--patchId", "test123", "--baseUrl", "https://custom.example.com/rest/v2/"]
    )
    assert request.base_url == "https://custom.example.com/rest/v2"


def test_parse_streaks_format_basic():
    """Test parsing basic streaks format."""
    data = {
        "streaks": [
            {
                "task_name": "task1",
                "latest_failure": {
                    "the_actual_variant_we_should_stop_using_the_incomprehensible_display_name_ones": "variant1"
                },
            },
            {
                "task_name": "task2",
                "latest_failure": {
                    "the_actual_variant_we_should_stop_using_the_incomprehensible_display_name_ones": "variant1"
                },
            },
            {
                "task_name": "task3",
                "latest_failure": {
                    "the_actual_variant_we_should_stop_using_the_incomprehensible_display_name_ones": "variant2"
                },
            },
        ]
    }

    result = _parse_streaks_format(data)
    assert len(result) == 2
    assert result[0].variant == "variant1"
    assert set(result[0].tasks) == {"task1", "task2"}
    assert result[1].variant == "variant2"
    assert list(result[1].tasks) == ["task3"]


def test_parse_streaks_format_filters_generated():
    """Test that variants ending with _generated are filtered out."""
    data = {
        "streaks": [
            {
                "task_name": "task1",
                "latest_failure": {
                    "the_actual_variant_we_should_stop_using_the_incomprehensible_display_name_ones": "variant1_generated"
                },
            },
            {
                "task_name": "task2",
                "latest_failure": {
                    "the_actual_variant_we_should_stop_using_the_incomprehensible_display_name_ones": "variant2"
                },
            },
        ]
    }

    result = _parse_streaks_format(data)
    assert len(result) == 1
    assert result[0].variant == "variant2"
    assert list(result[0].tasks) == ["task2"]


def test_parse_streaks_format_missing_variant():
    """Test that streaks without variant are skipped."""
    data = {
        "streaks": [
            {"task_name": "task1", "latest_failure": {}},
            {
                "task_name": "task2",
                "latest_failure": {
                    "the_actual_variant_we_should_stop_using_the_incomprehensible_display_name_ones": "variant1"
                },
            },
        ]
    }

    result = _parse_streaks_format(data)
    assert len(result) == 1
    assert result[0].variant == "variant1"


def test_parse_streaks_format_missing_task_name():
    """Test that streaks without task_name are skipped."""
    data = {
        "streaks": [
            {
                "latest_failure": {
                    "the_actual_variant_we_should_stop_using_the_incomprehensible_display_name_ones": "variant1"
                }
            },
            {
                "task_name": "task1",
                "latest_failure": {
                    "the_actual_variant_we_should_stop_using_the_incomprehensible_display_name_ones": "variant2"
                },
            },
        ]
    }

    result = _parse_streaks_format(data)
    assert len(result) == 1
    assert result[0].variant == "variant2"


def test_parse_streaks_format_empty():
    """Test empty streaks array."""
    data = {"streaks": []}
    result = _parse_streaks_format(data)
    assert result == []


def test_parse_streaks_format_deduplicates_tasks():
    """Test that duplicate tasks for same variant are deduplicated."""
    data = {
        "streaks": [
            {
                "task_name": "task1",
                "latest_failure": {
                    "the_actual_variant_we_should_stop_using_the_incomprehensible_display_name_ones": "variant1"
                },
            },
            {
                "task_name": "task1",
                "latest_failure": {
                    "the_actual_variant_we_should_stop_using_the_incomprehensible_display_name_ones": "variant1"
                },
            },
        ]
    }

    result = _parse_streaks_format(data)
    assert len(result) == 1
    assert list(result[0].tasks) == ["task1"]


def test_parse_waterfall_triage_from_stdin():
    """Test reading from stdin."""
    input_data = json.dumps(
        {
            "streaks": [
                {
                    "task_name": "task1",
                    "latest_failure": {
                        "the_actual_variant_we_should_stop_using_the_incomprehensible_display_name_ones": "variant1"
                    },
                }
            ]
        }
    )

    with patch("sys.stdin", StringIO(input_data)):
        result = parse_waterfall_triage_from_stdin()
        assert len(result) == 1
        assert result[0].variant == "variant1"


def test_parse_waterfall_triage_from_stdin_empty():
    """Test empty stdin."""
    with patch("sys.stdin", StringIO("")):
        result = parse_waterfall_triage_from_stdin()
        assert result == []


def test_parse_waterfall_triage_from_stdin_invalid_json():
    """Test invalid JSON raises CLIError."""
    with patch("sys.stdin", StringIO("not json")):
        with pytest.raises(CLIError, match="Invalid JSON"):
            parse_waterfall_triage_from_stdin()


def test_parse_waterfall_triage_from_stdin_missing_streaks():
    """Test missing streaks key raises CLIError."""
    with patch("sys.stdin", StringIO(json.dumps({"foo": "bar"}))):
        with pytest.raises(CLIError, match="must contain 'streaks'"):
            parse_waterfall_triage_from_stdin()


def test_get_oauth_token():
    """Test getting OAuth token from evergreen CLI."""
    mock_result = MagicMock()
    mock_result.stdout = "test_token_123\n"
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result):
        token = get_oauth_token()
        assert token == "test_token_123"


def test_get_oauth_token_empty():
    """Test empty token raises CLIError."""
    mock_result = MagicMock()
    mock_result.stdout = "\n"
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result):
        with pytest.raises(CLIError, match="empty token"):
            get_oauth_token()


def test_get_oauth_token_not_found():
    """Test missing evergreen CLI raises CLIError."""
    with patch("subprocess.run", side_effect=FileNotFoundError()):
        with pytest.raises(CLIError, match="evergreen CLI not found"):
            get_oauth_token()


def test_get_oauth_token_failure():
    """Test evergreen CLI failure raises CLIError."""
    error = subprocess.CalledProcessError(1, "cmd", stderr="error message")
    with patch("subprocess.run", side_effect=error):
        with pytest.raises(CLIError, match="failed"):
            get_oauth_token()


def test_main_dry_run():
    """Test main with dry run mode."""
    input_data = json.dumps(
        {
            "streaks": [
                {
                    "task_name": "task1",
                    "latest_failure": {
                        "the_actual_variant_we_should_stop_using_the_incomprehensible_display_name_ones": "variant1"
                    },
                }
            ]
        }
    )

    with patch("sys.stdin", StringIO(input_data)):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            exit_code = main(["--patchId", "test123", "--dryRun"])

            assert exit_code == 0
            output = json.loads(mock_stdout.getvalue())
            assert output["patch_id"] == "test123"
            assert output["summary"]["total"] == 1
            assert output["summary"]["success"] == 1


def test_main_empty_input():
    """Test main with empty input."""
    with patch("sys.stdin", StringIO("")):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            exit_code = main(["--patchId", "test123", "--dryRun"])

            assert exit_code == 0
            output = json.loads(mock_stdout.getvalue())
            assert output["summary"]["total"] == 0


def test_main_filters_generated():
    """Test that main filters out _generated variants."""
    input_data = json.dumps(
        {
            "streaks": [
                {
                    "task_name": "task1",
                    "latest_failure": {
                        "the_actual_variant_we_should_stop_using_the_incomprehensible_display_name_ones": "variant1_generated"
                    },
                },
                {
                    "task_name": "task2",
                    "latest_failure": {
                        "the_actual_variant_we_should_stop_using_the_incomprehensible_display_name_ones": "variant2"
                    },
                },
            ]
        }
    )

    with patch("sys.stdin", StringIO(input_data)):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            exit_code = main(["--patchId", "test123", "--dryRun"])

            assert exit_code == 0
            output = json.loads(mock_stdout.getvalue())
            assert output["summary"]["total"] == 1
            assert output["variant_tasks"][0]["variant"] == "variant2"
