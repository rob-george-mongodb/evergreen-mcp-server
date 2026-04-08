"""Standalone utilities for Evergreen waterfall triage workflows."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

import yaml

__version__ = "0.4.2"

PACKAGE_NAME = "evergreen_waterfall_triage"
USER_AGENT = f"{PACKAGE_NAME}/{__version__}"

EVERGREEN_CONFIG_FILE = Path.home() / ".evergreen.yml"

DEFAULT_OIDC_GRAPHQL_URL = "https://evergreen.corp.mongodb.com/graphql/query"
DEFAULT_API_KEY_GRAPHQL_URL = "https://evergreen.mongodb.com/graphql/query"
DEFAULT_UI_BASE_URL = "https://spruce.mongodb.com"
TASK_URL_PATH_TEMPLATE = "/task/{task_id}"

_cached_config: dict[str, Any] | None = None


class EvergreenConfigError(Exception):
    """Raised when the Evergreen config file cannot be parsed."""


def load_evergreen_config(
    *, use_cache: bool = True, ignore_errors: bool = False
) -> dict[str, Any]:
    """Load ``~/.evergreen.yml`` if it exists."""

    global _cached_config

    if use_cache and _cached_config is not None:
        return _cached_config

    config: dict[str, Any] = {}
    if EVERGREEN_CONFIG_FILE.exists():
        try:
            with EVERGREEN_CONFIG_FILE.open() as handle:
                config = yaml.safe_load(handle) or {}
        except Exception as exc:
            if ignore_errors:
                return {}
            raise EvergreenConfigError(
                f"Failed to parse {EVERGREEN_CONFIG_FILE}: {exc}"
            ) from exc

    if use_cache:
        _cached_config = config

    return config


from .urls import (  # noqa: E402
    TASK_URL_TEMPLATE_METADATA,
    TaskUrlTemplate,
    build_task_url,
    get_task_url_template,
    get_ui_base_url,
    normalize_base_url,
)

__all__ = [
    "AuthBootstrapError",
    "AuthenticatedGraphQLContext",
    "ConnectedEvergreenGraphQLClient",
    "DEFAULT_API_KEY_GRAPHQL_URL",
    "DEFAULT_OIDC_GRAPHQL_URL",
    "DEFAULT_UI_BASE_URL",
    "EVERGREEN_CONFIG_FILE",
    "EvergreenConfigError",
    "EvergreenGraphQLBootstrap",
    "GraphQLAuthMetadata",
    "PACKAGE_NAME",
    "TASK_URL_PATH_TEMPLATE",
    "TASK_URL_TEMPLATE_METADATA",
    "TaskUrlTemplate",
    "USER_AGENT",
    "build_task_url",
    "get_task_url_template",
    "get_ui_base_url",
    "graphql_client_context",
    "load_evergreen_config",
    "normalize_base_url",
    "resolve_graphql_endpoint",
]

_AUTH_EXPORTS = {
    "AuthBootstrapError",
    "AuthenticatedGraphQLContext",
    "ConnectedEvergreenGraphQLClient",
    "EvergreenGraphQLBootstrap",
    "GraphQLAuthMetadata",
    "graphql_client_context",
    "resolve_graphql_endpoint",
}


def __getattr__(name: str) -> Any:
    """Lazily expose auth helpers without importing optional deps at import time."""

    if name in _AUTH_EXPORTS:
        module = import_module(".auth", __name__)
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
