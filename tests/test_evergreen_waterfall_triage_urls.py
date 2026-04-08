import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evergreen_waterfall_triage.urls import build_task_url, get_task_url_template, normalize_base_url


def test_normalize_base_url_trims_trailing_slash():
    assert normalize_base_url("https://spruce.mongodb.com///") == "https://spruce.mongodb.com"


def test_build_task_url_uses_default_base_url():
    assert (
        build_task_url("task_123", config={})
        == "https://spruce.mongodb.com/task/task_123"
    )


def test_build_task_url_respects_configured_base_url():
    template = get_task_url_template(config={"ui_server_host": "https://example.com/"})
    assert template.template_url == "https://example.com/task/{task_id}"
    assert template.build_task_url("task 123") == "https://example.com/task/task%20123"
