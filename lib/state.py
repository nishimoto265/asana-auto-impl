"""State file management (tmp/state.json)."""

import json
import logging
from pathlib import Path
from typing import Any

from lib.config import STATE_FILE

logger = logging.getLogger("asana_poller")

DEFAULT_STATE: dict[str, Any] = {
    "known_task_gids": [],
    "running_tasks": {},
    "completed_task_gids": [],
}


def load_state() -> dict:
    """Load state.json, returning a fresh default on any error."""
    if not STATE_FILE.exists():
        logger.info("state.json not found – initialising.")
        save_state(DEFAULT_STATE)
        return dict(DEFAULT_STATE)
    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
        for key in DEFAULT_STATE:
            if key not in data:
                raise ValueError(f"Missing key: {key}")
            expected_type = type(DEFAULT_STATE[key])
            if not isinstance(data[key], expected_type):
                raise ValueError(
                    f"Invalid type for key {key}: expected {expected_type.__name__}"
                )
        return data
    except Exception as exc:
        logger.warning("state.json corrupted (%s) – reinitialising.", exc)
        save_state(DEFAULT_STATE)
        return dict(DEFAULT_STATE)


def save_state(state: dict) -> None:
    """Atomically write state to disk."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    tmp.replace(STATE_FILE)
