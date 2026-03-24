"""Asana API helpers."""

import logging
import time

import requests

from lib.config import (
    ASANA_BASE_URL,
    ASANA_PAT,
    ASANA_PROJECT_GIDS,
    ASANA_WORKSPACE_GID,
)

logger = logging.getLogger("asana_poller")


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {ASANA_PAT}"}


def _asana_get(path: str, params: dict | None = None) -> dict:
    """GET from Asana API with basic rate-limit handling."""
    url = f"{ASANA_BASE_URL}{path}"
    while True:
        resp = requests.get(url, headers=_headers(), params=params, timeout=30)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "60"))
            logger.warning("Rate limited – waiting %ds", retry_after)
            time.sleep(retry_after)
            continue
        resp.raise_for_status()
        return resp.json()


def _paginate(initial_data: dict, filter_fn=None) -> list[dict]:
    """Consume all pages from an Asana API response.

    Args:
        initial_data: First page response from _asana_get.
        filter_fn: Optional callable to filter each task dict.

    Returns:
        Collected list of task dicts across all pages.
    """
    results: list[dict] = []

    def _collect(data: dict) -> None:
        for t in data.get("data", []):
            if filter_fn is None or filter_fn(t):
                results.append(t)

    _collect(initial_data)
    data = initial_data

    while data.get("next_page"):
        next_uri = data["next_page"]["uri"]
        resp = requests.get(next_uri, headers=_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        _collect(data)

    return results


def get_my_user_gid() -> str:
    data = _asana_get("/users/me")
    return data["data"]["gid"]


def get_my_incomplete_tasks(assignee_gid: str) -> list[dict]:
    """Return list of incomplete task dicts assigned to the user.

    If ASANA_PROJECT_GIDS is set, returns tasks from those projects.
    Otherwise uses the user_task_list endpoint (workspace-wide).
    """
    if ASANA_PROJECT_GIDS:
        all_tasks: list[dict] = []
        seen_gids: set[str] = set()
        for project_gid in ASANA_PROJECT_GIDS:
            params = {
                "project": project_gid,
                "completed_since": "now",
                "opt_fields": "gid,name,assignee",
                "limit": 100,
            }
            data = _asana_get("/tasks", params=params)
            tasks = _paginate(
                data,
                filter_fn=lambda t: (
                    t.get("assignee") and t["assignee"].get("gid") == assignee_gid
                ),
            )
            for t in tasks:
                if t["gid"] not in seen_gids:
                    seen_gids.add(t["gid"])
                    all_tasks.append(t)
        return all_tasks
    else:
        utl_data = _asana_get(
            f"/users/{assignee_gid}/user_task_list",
            params={"workspace": ASANA_WORKSPACE_GID},
        )
        utl_gid = utl_data["data"]["gid"]
        params = {
            "completed_since": "now",
            "opt_fields": "gid,name",
            "limit": 100,
        }
        data = _asana_get(f"/user_task_lists/{utl_gid}/tasks", params=params)
        return _paginate(data)


def get_task_detail(gid: str) -> dict:
    data = _asana_get(
        f"/tasks/{gid}", params={"opt_fields": "gid,name,notes,permalink_url"}
    )
    return data["data"]
