#!/usr/bin/env python3
"""Asana polling daemon.

Runs inside a tmux session "asana-poller".
Periodically fetches incomplete tasks assigned to the current user,
detects new ones, and spawns run_task.sh in a dedicated tmux session.
"""

import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

load_dotenv()

ASANA_PAT = os.environ.get("ASANA_PAT", "")
ASANA_WORKSPACE_GID = os.environ.get("ASANA_WORKSPACE_GID", "")
ASANA_PROJECT_GID = os.environ.get("ASANA_PROJECT_GID", "")
POLL_INTERVAL = int(os.environ.get("ASANA_POLL_INTERVAL_SEC", "60"))
LOG_DIR = Path(os.environ.get("LOG_DIR", "./logs")).resolve()
STATE_FILE = Path(os.environ.get("TMP_DIR", "./tmp")).resolve() / "state.json"

SCRIPT_DIR = Path(__file__).resolve().parent
RUN_TASK_SH = SCRIPT_DIR / "run_task.sh"

ASANA_BASE_URL = "https://app.asana.com/api/1.0"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_DIR.mkdir(parents=True, exist_ok=True)
(LOG_DIR / "tasks").mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("asana_poller")
logger.setLevel(logging.DEBUG)

_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

_fh = logging.FileHandler(LOG_DIR / "poller.log")
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(_fmt)
logger.addHandler(_fh)

_sh = logging.StreamHandler(sys.stdout)
_sh.setLevel(logging.INFO)
_sh.setFormatter(_fmt)
logger.addHandler(_sh)

# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

DEFAULT_STATE = {
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
        # Validate keys
        for key in DEFAULT_STATE:
            if key not in data:
                raise ValueError(f"Missing key: {key}")
            expected_type = type(DEFAULT_STATE[key])
            if not isinstance(data[key], expected_type):
                raise ValueError(f"Invalid type for key {key}: expected {expected_type.__name__}")
        return data
    except Exception as exc:
        logger.warning("state.json corrupted (%s) – reinitialising.", exc)
        save_state(DEFAULT_STATE)
        return dict(DEFAULT_STATE)


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    tmp.replace(STATE_FILE)

# ---------------------------------------------------------------------------
# Asana API helpers
# ---------------------------------------------------------------------------


def _headers() -> dict:
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


def get_my_user_gid() -> str:
    data = _asana_get("/users/me")
    return data["data"]["gid"]


def get_my_incomplete_tasks(assignee_gid: str) -> list[dict]:
    """Return list of incomplete task dicts assigned to the user.

    If ASANA_PROJECT_GID is set, only returns tasks from that project.
    Otherwise uses the user_task_list endpoint (workspace-wide).
    """
    all_tasks: list[dict] = []

    if ASANA_PROJECT_GID:
        # Project-scoped: fetch all incomplete tasks, then filter by assignee locally
        params = {
            "project": ASANA_PROJECT_GID,
            "completed_since": "now",
            "opt_fields": "gid,name,assignee",
            "limit": 100,
        }
        data = _asana_get("/tasks", params=params)
        for t in data.get("data", []):
            if t.get("assignee") and t["assignee"].get("gid") == assignee_gid:
                all_tasks.append(t)

        while data.get("next_page"):
            next_uri = data["next_page"]["uri"]
            resp = requests.get(
                next_uri,
                headers=_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            for t in data.get("data", []):
                if t.get("assignee") and t["assignee"].get("gid") == assignee_gid:
                    all_tasks.append(t)
    else:
        # Workspace-wide: use user_task_list endpoint
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
        all_tasks.extend(data.get("data", []))

        while data.get("next_page"):
            next_uri = data["next_page"]["uri"]
            resp = requests.get(
                next_uri,
                headers=_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            all_tasks.extend(data.get("data", []))

    return all_tasks


def get_task_detail(gid: str) -> dict:
    data = _asana_get(f"/tasks/{gid}", params={"opt_fields": "gid,name,notes,permalink_url"})
    return data["data"]

# ---------------------------------------------------------------------------
# Task launcher
# ---------------------------------------------------------------------------


def _to_kebab(name: str) -> str:
    """Convert a task name to kebab-case directory name."""
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s if s else "unnamed"


def _get_claude_session_id(gid: str) -> str | None:
    """Find the Claude session ID by looking at ~/.claude/projects/ for the work dir."""
    state = load_state()
    task_info = state.get("running_tasks", {}).get(gid, {})
    work_dir = task_info.get("work_dir", "")

    if not work_dir:
        logger.debug("No work_dir in state for task %s", gid)
        return None

    # Claude project dir name: non-alphanumeric chars (except -) replaced by -
    project_dir_name = re.sub(r"[^a-zA-Z0-9\-]", "-", work_dir)

    claude_projects = Path.home() / ".claude" / "projects" / project_dir_name
    if not claude_projects.exists():
        logger.debug("Claude project dir not found: %s", claude_projects)
        return None

    # Find the most recently modified .jsonl file
    jsonl_files = sorted(claude_projects.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if jsonl_files:
        return jsonl_files[0].stem  # filename without extension = session ID
    return None


def _send_claude_commands(gid: str, session_name: str, task_name: str, task_url: str) -> None:
    """Wait for run_task.sh setup to finish, then send claude + /mai via tmux send-keys."""
    claude_cmd = os.environ.get("CLAUDE_CMD", "claude")
    # Wait for run_task.sh setup to finish (marker file)
    marker = SCRIPT_DIR / "tmp" / f"setup_done_{gid}"
    for _ in range(360):  # max 6 min wait
        if marker.exists():
            break
        time.sleep(1)
    else:
        logger.error("Timeout waiting for setup of task %s", gid)
        return

    time.sleep(2)

    try:
        # Start claude with -n for session naming
        claude_launch = f"{claude_cmd} -n '{task_name}'"
        subprocess.run(["tmux", "send-keys", "-t", session_name,
                        "-l", claude_launch], check=True)
        subprocess.run(["tmux", "send-keys", "-t", session_name, "Enter"], check=True)
        time.sleep(8)

        # Enter twice for initial prompts
        subprocess.run(["tmux", "send-keys", "-t", session_name, "", "Enter"], check=True)
        time.sleep(1)
        subprocess.run(["tmux", "send-keys", "-t", session_name, "", "Enter"], check=True)
        time.sleep(2)

        # Bypass permission
        subprocess.run(["tmux", "send-keys", "-t", session_name, "", "Enter"], check=True)
        time.sleep(1)

        # Send /mai with Asana URL in one message
        mai_cmd = f"/mai {task_url}"
        subprocess.run(["tmux", "send-keys", "-t", session_name, "-l", mai_cmd], check=True)
        subprocess.run(["tmux", "send-keys", "-t", session_name, "Enter"], check=True)

        logger.info("Claude + /mai sent to task %s (%s)", gid, task_url)

        # Wait for Claude to create session file, then retrieve ID
        time.sleep(10)
        claude_session_id = _get_claude_session_id(gid)
        if claude_session_id:
            state = load_state()
            if gid in state.get("running_tasks", {}):
                state["running_tasks"][gid]["claude_session"] = claude_session_id
                save_state(state)
                logger.info("Claude session ID for task %s: %s", gid, claude_session_id)
        else:
            logger.warning("Could not retrieve Claude session ID for task %s", gid)
    except subprocess.CalledProcessError as exc:
        logger.error("Failed to send claude commands to task %s: %s", gid, exc)


def launch_task(gid: str, task_name: str, state: dict) -> None:
    """Spawn run_task.sh in a new tmux session for the given task GID."""
    session_name = f"task-{gid}"
    task_log = LOG_DIR / "tasks" / f"{gid}.log"

    task_log.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Launching task %s (%s) in tmux session '%s'", gid, task_name, session_name)

    # Kill stale tmux session if it exists
    check = subprocess.run(["tmux", "has-session", "-t", session_name],
                           capture_output=True)
    if check.returncode == 0:
        logger.warning("tmux session '%s' already exists, killing it", session_name)
        subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True)

    cmd = [
        "tmux", "new-session", "-d", "-s", session_name,
        f"bash {RUN_TASK_SH} {gid}",
    ]
    env = os.environ.copy()
    env["TASK_LOG"] = str(task_log)

    try:
        subprocess.run(cmd, check=True, env=env, timeout=10)
        logger.info("tmux session started: tmux attach -t %s", session_name)

        # Record in state
        if "running_tasks" not in state:
            state["running_tasks"] = {}
        # Compute work_dir (same logic as run_task.sh)
        repo_path = os.path.expanduser(os.environ.get("REPO_PATH", "~/project"))
        if task_name:
            dir_name = re.sub(r'[/:*?"<>|\\]', '-', task_name)
            dir_name = re.sub(r'\s+', '-', dir_name)
            dir_name = re.sub(r'-+', '-', dir_name).strip('-')
        else:
            dir_name = gid
        work_dir = os.path.join(repo_path, dir_name or gid)

        task_url = f"https://app.asana.com/0/0/{gid}/f"

        state["running_tasks"][gid] = {
            "name": task_name,
            "tmux_session": session_name,
            "work_dir": work_dir,
        }
        save_state(state)

        # Start a background thread to send claude + /mai after setup completes
        import threading
        t = threading.Thread(target=_send_claude_commands, args=(gid, session_name, task_name, task_url), daemon=True)
        t.start()
    except subprocess.CalledProcessError as exc:
        logger.error("Failed to create tmux session for task %s: %s", gid, exc)
    except subprocess.TimeoutExpired:
        logger.error("Timeout creating tmux session for task %s", gid)

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

    # Build a map of gid -> task name for new tasks
    task_map = {t["gid"]: t.get("name", "") for t in tasks}

    for gid in new_gids:
        task_name = task_map.get(gid, gid)
        state["known_task_gids"].append(gid)
        save_state(state)
        launch_task(gid, task_name, state)

    return state


PID_FILE = SCRIPT_DIR / "tmp" / "poller.pid"


def _acquire_lock() -> None:
    """Ensure only one poller instance runs at a time."""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    if PID_FILE.exists():
        old_pid = int(PID_FILE.read_text().strip())
        # Check if process is still alive
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
