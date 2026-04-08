"""URL helpers for Evergreen waterfall triage resources."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import quote

from . import DEFAULT_UI_BASE_URL, TASK_URL_PATH_TEMPLATE, load_evergreen_config


def normalize_base_url(url: str | None) -> str:
    """Normalize a base URL by trimming trailing slashes."""

    return (url or DEFAULT_UI_BASE_URL).strip().rstrip("/")


def get_ui_base_url(config: Mapping[str, Any] | None = None) -> str:
    """Return the configured Evergreen UI base URL or the default Spruce URL."""

    config_data = (
        config if config is not None else load_evergreen_config(ignore_errors=True)
    )
    return normalize_base_url(config_data.get("ui_server_host"))


@dataclass(frozen=True)
class TaskUrlTemplate:
    """Template metadata for Evergreen task URLs."""

    base_url: str
    path_template: str = TASK_URL_PATH_TEMPLATE

    @property
    def template_url(self) -> str:
        """Return the concrete URL template string."""

        return f"{self.base_url}{self.path_template}"

    def build_task_url(self, task_id: str) -> str:
        """Build a deterministic Spruce task URL."""

        normalized_task_id = task_id.strip()
        if not normalized_task_id:
            raise ValueError("task_id is required")

        task_path = self.path_template.format(
            task_id=quote(normalized_task_id, safe=""),
        )
        return f"{self.base_url}{task_path}"


TASK_URL_TEMPLATE_METADATA = {
    "default_base_url": DEFAULT_UI_BASE_URL,
    "path_template": TASK_URL_PATH_TEMPLATE,
}


def get_task_url_template(
    *, config: Mapping[str, Any] | None = None, ui_base_url: str | None = None
) -> TaskUrlTemplate:
    """Return task URL template metadata with a resolved base URL."""

    base_url = (
        normalize_base_url(ui_base_url) if ui_base_url else get_ui_base_url(config)
    )
    return TaskUrlTemplate(base_url=base_url)


def build_task_url(
    task_id: str,
    *,
    config: Mapping[str, Any] | None = None,
    ui_base_url: str | None = None,
) -> str:
    """Build a task URL from a task identifier."""

    template = get_task_url_template(config=config, ui_base_url=ui_base_url)
    return template.build_task_url(task_id)
