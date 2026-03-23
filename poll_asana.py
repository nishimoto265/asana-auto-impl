#!/usr/bin/env python3
"""Asana polling daemon.

Runs inside a tmux session "asana-poller".
Periodically fetches incomplete tasks assigned to the current user,
detects new ones, and spawns run_task.sh in a dedicated tmux session.
"""

import os
import sys
import time
from pathlib import Path

import requests

from lib.asana_api import get_my_incomplete_tasks, get_my_user_gid
from lib.config import ASANA_PAT, ASANA_PROJECT_GID, ASANA_WORKSPACE_GID, POLL_INTERVAL
from lib.launcher import launch_task
from lib.logging_setup import setup_logging
from lib.state import load_state, save_state
from lib.template import ensure_template

SCRIPT_DIR = Path(__file__).resolve().parent
PID_FILE = SCRIPT_DIR / "tmp" / "poller.pid"

logger = setup_logging()


# ---------------------------------------------------------------------------
# Polling loop
# ---------------------------------------------------------------------------


def detect_and_launch(assignee_gid: str, state: dict) -> dict:
    """One polling cycle: fetch tasks, detect new, launch, update state."""
    tasks = get_my_incomplete_tasks(assignee_gid)
    current_gids = {t["gid"] for t in tasks}
    known = set(state["known_task_gids"])

    new_gids = current_gids - known
    if new_gids:
        logger.info("New tasks detected: %s", new_gids)
    else:
        logger.debug("No new tasks. (current=%d, known=%d)", len(current_gids), len(known))

    task_map = {t["gid"]: t.get("name", "") for t in tasks}

    for gid in new_gids:
        task_name = task_map.get(gid, gid)
        state["known_task_gids"].append(gid)
        save_state(state)
        launch_task(gid, task_name, state)

    return state


def _acquire_lock() -> None:
    """Ensure only one poller instance runs at a time."""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    if PID_FILE.exists():
        old_pid = int(PID_FILE.read_text().strip())
        try:
            os.kill(old_pid, 0)
            logger.error("Another poller is already running (PID %d). Exiting.", old_pid)
            sys.exit(1)
        except OSError:
            logger.warning("Stale PID file found (PID %d not running). Removing.", old_pid)
    PID_FILE.write_text(str(os.getpid()))


def main() -> None:
    _acquire_lock()

    if not ASANA_PAT:
        logger.error("ASANA_PAT is not set. Exiting.")
        sys.exit(1)
    if not ASANA_WORKSPACE_GID:
        logger.error("ASANA_WORKSPACE_GID is not set. Exiting.")
        sys.exit(1)

    if ASANA_PROJECT_GID:
        logger.info("Filtering by project GID: %s", ASANA_PROJECT_GID)
    else:
        logger.info("Watching all tasks in workspace (no project filter)")

    logger.info("Starting Asana poller (interval=%ds)", POLL_INTERVAL)

    ensure_template()

    try:
        assignee_gid = get_my_user_gid()
        logger.info("Authenticated as user %s", assignee_gid)
    except Exception as exc:
        logger.error("Failed to authenticate with Asana: %s", exc)
        sys.exit(1)

    state = load_state()

    # On first launch, register existing tasks so we don't re-trigger them
    if not state["known_task_gids"]:
        logger.info("First run – registering existing tasks as known.")
        try:
            tasks = get_my_incomplete_tasks(assignee_gid)
            state["known_task_gids"] = [t["gid"] for t in tasks]
            save_state(state)
            logger.info("Registered %d existing tasks.", len(state["known_task_gids"]))
        except Exception as exc:
            logger.warning("Failed to seed known tasks: %s", exc)

    while True:
        try:
            state = detect_and_launch(assignee_gid, state)
        except requests.exceptions.RequestException as exc:
            logger.error("API error during poll: %s", exc)
        except Exception as exc:
            logger.error("Unexpected error during poll: %s", exc)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
