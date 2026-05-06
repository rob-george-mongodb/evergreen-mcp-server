"""Tests for artifact download CLI."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from evergreen_waterfall_triage.artifact_download_cli import (
    CLIError,
    ArtifactDownloadRequest,
    download_artifacts_for_task,
    extract_task_ids,
    load_triage_json,
    main,
    parse_request,
    run_downloads,
)


class TestParseRequest(unittest.TestCase):
    def test_required_artifact_download_dir(self):
        with pytest.raises(CLIError, match="--artifactDownloadDir"):
            parse_request([])

    def test_parses_all_arguments(self):
        request = parse_request(
            [
                "--artifactDownloadDir",
                "/tmp/artifacts",
                "--artifact_name",
                "logs",
                "--artifact_name",
                "results",
                "--shallow",
                "--triageJson",
                "/tmp/triage.json",
            ]
        )
        assert request.artifact_download_dir == "/tmp/artifacts"
        assert request.artifact_names == ["logs", "results"]
        assert request.shallow is True
        assert request.triage_json_path == "/tmp/triage.json"

    def test_defaults(self):
        request = parse_request(["--artifactDownloadDir", "/tmp/artifacts"])
        assert request.artifact_names == []
        assert request.shallow is False
        assert request.triage_json_path is None


class TestExtractTaskIds(unittest.TestCase):
    def test_extracts_task_ids_from_streaks(self):
        triage_data = {
            "streaks": [
                {
                    "latest_failure": {
                        "task_id": "task-1",
                    }
                },
                {
                    "latest_failure": {
                        "task_id": "task-2",
                    }
                },
            ]
        }
        task_ids = extract_task_ids(triage_data)
        assert task_ids == ["task-1", "task-2"]

    def test_deduplicates_task_ids(self):
        triage_data = {
            "streaks": [
                {
                    "latest_failure": {
                        "task_id": "task-1",
                    }
                },
                {
                    "latest_failure": {
                        "task_id": "task-1",
                    }
                },
            ]
        }
        task_ids = extract_task_ids(triage_data)
        assert task_ids == ["task-1"]

    def test_raises_on_missing_streaks(self):
        triage_data = {}
        with pytest.raises(CLIError, match="'streaks' key not found"):
            extract_task_ids(triage_data)

    def test_raises_on_invalid_streaks_type(self):
        triage_data = {"streaks": "not a list"}
        with pytest.raises(CLIError, match="'streaks' must be a list"):
            extract_task_ids(triage_data)

    def test_raises_on_missing_latest_failure(self):
        triage_data = {"streaks": [{}]}
        with pytest.raises(CLIError, match="missing 'latest_failure'"):
            extract_task_ids(triage_data)

    def test_raises_on_missing_task_id(self):
        triage_data = {"streaks": [{"latest_failure": {}}]}
        with pytest.raises(CLIError, match="missing 'task_id'"):
            extract_task_ids(triage_data)

    def test_raises_on_invalid_task_id_type(self):
        triage_data = {"streaks": [{"latest_failure": {"task_id": 123}}]}
        with pytest.raises(CLIError, match="'task_id' is not a string"):
            extract_task_ids(triage_data)


class TestDownloadArtifactsForTask(unittest.TestCase):
    def test_builds_correct_command_all_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            download_dir = Path(tmp)
            
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    stdout="success",
                    stderr="",
                    returncode=0,
                )
                result = download_artifacts_for_task(
                    task_id="task-123",
                    download_dir=download_dir,
                    artifact_names=[],
                    shallow=False,
                )
            
            assert result["success"] is True
            assert result["task_id"] == "task-123"
            assert "task-123" in result["download_dir"]
            
            call_args = mock_run.call_args[0][0]
            assert "evergreen" in call_args
            assert "fetch" in call_args
            assert "--task" in call_args
            assert "task-123" in call_args
            assert "--artifacts" in call_args
            assert "--shallow" not in call_args

    def test_builds_correct_command_specific_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            download_dir = Path(tmp)
            
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    stdout="success",
                    stderr="",
                    returncode=0,
                )
                result = download_artifacts_for_task(
                    task_id="task-123",
                    download_dir=download_dir,
                    artifact_names=["logs", "results"],
                    shallow=True,  # ignored when using artifact_name
                )
            
            assert result["success"] is True
            
            call_args = mock_run.call_args[0][0]
            assert "--artifact_name" in call_args
            assert "logs" in call_args
            assert "results" in call_args
            # --shallow only applies to --artifacts, not --artifact_name
            assert "--shallow" not in call_args
            assert "--artifacts" not in call_args

    def test_handles_subprocess_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            download_dir = Path(tmp)
            
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["evergreen", "fetch"],
                    stderr="error downloading",
                )
                result = download_artifacts_for_task(
                    task_id="task-123",
                    download_dir=download_dir,
                    artifact_names=[],
                    shallow=False,
                )
            
            assert result["success"] is False
            assert "error downloading" in result["error"]
            assert result["returncode"] == 1

    def test_handles_unexpected_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            download_dir = Path(tmp)
            
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = RuntimeError("unexpected error")
                result = download_artifacts_for_task(
                    task_id="task-123",
                    download_dir=download_dir,
                    artifact_names=[],
                    shallow=False,
                )
            
            assert result["success"] is False
            assert "unexpected error" in result["error"]


class TestLoadTriageJson(unittest.TestCase):
    def test_loads_from_file(self):
        triage_data = {"streaks": [{"latest_failure": {"task_id": "task-1"}}]}
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(triage_data, f)
            f.flush()
            
            request = ArtifactDownloadRequest(
                triage_json_path=f.name,
                artifact_download_dir="/tmp",
                artifact_names=[],
                shallow=False,
            )
            
            loaded = load_triage_json(request)
            assert loaded == triage_data
            
            Path(f.name).unlink()

    def test_loads_from_stdin(self):
        triage_data = {"streaks": [{"latest_failure": {"task_id": "task-1"}}]}
        
        request = ArtifactDownloadRequest(
            triage_json_path=None,
            artifact_download_dir="/tmp",
            artifact_names=[],
            shallow=False,
        )
        
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.read.return_value = json.dumps(triage_data)
            loaded = load_triage_json(request)
            assert loaded == triage_data

    def test_raises_on_file_not_found(self):
        request = ArtifactDownloadRequest(
            triage_json_path="/nonexistent/file.json",
            artifact_download_dir="/tmp",
            artifact_names=[],
            shallow=False,
        )
        
        with pytest.raises(CLIError, match="Triage JSON file not found"):
            load_triage_json(request)

    def test_raises_on_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json")
            f.flush()
            
            request = ArtifactDownloadRequest(
                triage_json_path=f.name,
                artifact_download_dir="/tmp",
                artifact_names=[],
                shallow=False,
            )
            
            with pytest.raises(CLIError, match="Invalid JSON"):
                load_triage_json(request)
            
            Path(f.name).unlink()


class TestRunDownloads(unittest.TestCase):
    def test_returns_empty_results_for_no_tasks(self):
        request = ArtifactDownloadRequest(
            triage_json_path=None,
            artifact_download_dir="/tmp",
            artifact_names=[],
            shallow=False,
        )
        
        triage_data = {"streaks": []}
        
        with patch(
            "evergreen_waterfall_triage.artifact_download_cli.load_triage_json",
            return_value=triage_data,
        ):
            result = run_downloads(request)
        
        assert result["success"] is True
        assert result["task_count"] == 0
        assert result["results"] == []

    def test_downloads_artifacts_for_multiple_tasks(self):
        triage_data = {
            "streaks": [
                {"latest_failure": {"task_id": "task-1"}},
                {"latest_failure": {"task_id": "task-2"}},
            ]
        }
        
        request = ArtifactDownloadRequest(
            triage_json_path=None,
            artifact_download_dir="/tmp",
            artifact_names=["logs"],
            shallow=True,
        )
        
        with tempfile.TemporaryDirectory() as tmp:
            request = ArtifactDownloadRequest(
                triage_json_path=None,
                artifact_download_dir=tmp,
                artifact_names=["logs"],
                shallow=True,
            )
            
            with patch(
                "evergreen_waterfall_triage.artifact_download_cli.load_triage_json",
                return_value=triage_data,
            ):
                with patch(
                    "evergreen_waterfall_triage.artifact_download_cli.download_artifacts_for_task"
                ) as mock_download:
                    mock_download.side_effect = [
                        {
                            "task_id": "task-1",
                            "success": True,
                            "download_dir": f"{tmp}/task-1",
                        },
                        {
                            "task_id": "task-2",
                            "success": True,
                            "download_dir": f"{tmp}/task-2",
                        },
                    ]
                    
                    result = run_downloads(request)
            
            assert result["success"] is True
            assert result["task_count"] == 2
            assert result["success_count"] == 2
            assert len(result["results"]) == 2

    def test_reports_partial_failures(self):
        triage_data = {
            "streaks": [
                {"latest_failure": {"task_id": "task-1"}},
                {"latest_failure": {"task_id": "task-2"}},
            ]
        }
        
        with tempfile.TemporaryDirectory() as tmp:
            request = ArtifactDownloadRequest(
                triage_json_path=None,
                artifact_download_dir=tmp,
                artifact_names=[],
                shallow=False,
            )
            
            with patch(
                "evergreen_waterfall_triage.artifact_download_cli.load_triage_json",
                return_value=triage_data,
            ):
                with patch(
                    "evergreen_waterfall_triage.artifact_download_cli.download_artifacts_for_task"
                ) as mock_download:
                    mock_download.side_effect = [
                        {
                            "task_id": "task-1",
                            "success": True,
                            "download_dir": f"{tmp}/task-1",
                        },
                        {
                            "task_id": "task-2",
                            "success": False,
                            "download_dir": f"{tmp}/task-2",
                            "error": "download failed",
                        },
                    ]
                    
                    result = run_downloads(request)
            
            assert result["success"] is False
            assert result["task_count"] == 2
            assert result["success_count"] == 1


class TestMain(unittest.TestCase):
    def test_exits_successfully_on_success(self):
        triage_data = {
            "streaks": [{"latest_failure": {"task_id": "task-1"}}]
        }
        
        with tempfile.TemporaryDirectory() as tmp:
            triage_file = Path(tmp) / "triage.json"
            triage_file.write_text(json.dumps(triage_data))
            
            with patch(
                "evergreen_waterfall_triage.artifact_download_cli.download_artifacts_for_task"
            ) as mock_download:
                mock_download.return_value = {
                    "task_id": "task-1",
                    "success": True,
                    "download_dir": f"{tmp}/task-1",
                }
                
                exit_code = main(
                    [
                        "--triageJson",
                        str(triage_file),
                        "--artifactDownloadDir",
                        tmp,
                    ]
                )
            
            assert exit_code == 0

    def test_exits_with_error_on_failure(self):
        triage_data = {
            "streaks": [{"latest_failure": {"task_id": "task-1"}}]
        }
        
        with tempfile.TemporaryDirectory() as tmp:
            triage_file = Path(tmp) / "triage.json"
            triage_file.write_text(json.dumps(triage_data))
            
            with patch(
                "evergreen_waterfall_triage.artifact_download_cli.download_artifacts_for_task"
            ) as mock_download:
                mock_download.return_value = {
                    "task_id": "task-1",
                    "success": False,
                    "download_dir": f"{tmp}/task-1",
                    "error": "download failed",
                }
                
                exit_code = main(
                    [
                        "--triageJson",
                        str(triage_file),
                        "--artifactDownloadDir",
                        tmp,
                    ]
                )
            
            assert exit_code == 1

    def test_exits_with_cli_error_on_missing_required_arg(self):
        exit_code = main([])
        assert exit_code == 2


class TestSampleInput(unittest.TestCase):
    """Test with the sample JSON provided by the user."""
    
    def test_processes_sample_json(self):
        """Verify the CLI can process the sample_4_u_ai.json structure."""
        sample_path = Path(__file__).parent.parent / "sample_4_u_ai.json"
        
        if not sample_path.exists():
            self.skipTest("sample_4_u_ai.json not found")
        
        with open(sample_path) as f:
            triage_data = json.load(f)
        
        task_ids = extract_task_ids(triage_data)
        
        # Should extract all 11 unique task IDs from the sample
        assert len(task_ids) == 11
        
        # Verify first task ID matches expected
        expected_first_id = (
            "mms_v20260506_e2e_nds_corruption_detection_generated_"
            "E2E_NDS_Data_Validation_Large_AWS_MDB_8_GENERATED_"
            "51af1646595c788aeb9510b7870aa33ddcf8199b_26_05_05_21_39_09"
        )
        assert task_ids[0] == expected_first_id