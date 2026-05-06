"""Low-level API wrapper for Evergreen patch operations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Sequence

import aiohttp

logger = logging.getLogger(__name__)


class PatchAPIError(Exception):
    """Error from patch API operations."""

    pass


@dataclass(frozen=True)
class VariantTasks:
    """Tasks to add to a variant in a patch."""

    variant: str
    tasks: Sequence[str]


@dataclass(frozen=True)
class PatchAddTasksRequest:
    """Request to add tasks to an existing patch."""

    patch_id: str
    variant_tasks: Sequence[VariantTasks]
    dry_run: bool = False
    base_url: str = "https://evergreen.corp.mongodb.com/rest/v2"


async def add_tasks_to_patch(
    request: PatchAddTasksRequest,
    token: str,
) -> dict[str, Any]:
    """Add tasks to an existing patch via REST API.

    Args:
        request: Patch add tasks request configuration
        token: OAuth bearer token

    Returns:
        Summary dict with results for each variant
    """
    if request.dry_run:
        return {
            "patch_id": request.patch_id,
            "variant_tasks": [
                {"variant": vt.variant, "tasks": list(vt.tasks), "dry_run": True}
                for vt in request.variant_tasks
            ],
            "summary": {
                "total": len(request.variant_tasks),
                "success": len(request.variant_tasks),
                "failed": 0,
            },
        }

    results = []
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        for vt in request.variant_tasks:
            result = {
                "variant": vt.variant,
                "tasks": list(vt.tasks),
                "success": False,
            }

            try:
                url = f"{request.base_url}/patches/{request.patch_id}/tasks"
                payload = {
                    "variant": vt.variant,
                    "tasks": list(vt.tasks),
                }

                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status in (200, 201):
                        result["success"] = True
                        result["response"] = await response.json()
                    else:
                        text = await response.text()
                        result["error"] = f"HTTP {response.status}: {text}"
                        logger.error(
                            "Failed to add tasks to patch %s for variant %s: %s",
                            request.patch_id,
                            vt.variant,
                            result["error"],
                        )
            except Exception as e:
                result["error"] = str(e)
                logger.exception(
                    "Exception adding tasks to patch %s for variant %s",
                    request.patch_id,
                    vt.variant,
                )

            results.append(result)

    success_count = sum(1 for r in results if r["success"])
    failed_count = len(results) - success_count

    return {
        "patch_id": request.patch_id,
        "variant_tasks": results,
        "summary": {
            "total": len(results),
            "success": success_count,
            "failed": failed_count,
        },
    }
