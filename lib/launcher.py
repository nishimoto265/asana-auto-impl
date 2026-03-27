"""Task launcher – spawns run_task.sh in tmux sessions."""

import logging
import os
import re
import shlex
import subprocess
import threading
import time
from pathlib import Path

from lib.config import (
    CLAUDE_CMD,
    CLAUDE_EXTRA_MSG,
    CLAUDE_STARTUP_CMD,
    CLAUDE_STARTUP_WAIT,
    LOG_DIR,
    REPO_PATH,
    RUN_TASK_SH,
    SCRIPT_DIR,
)
from lib.dirnames import to_safe_dirname
from lib.state import load_state, save_state

logger = logging.getLogger("asana_poller")


def _get_claude_session_id(gid: str) -> str | None:
    """Find the Claude session ID by looking at ~/.claude/projects/ for the work dir."""
    state = load_state()
    task_info = state.get("running_tasks", {}).get(gid, {})
    work_dir = task_info.get("work_dir", "")

    if not work_dir:
        logger.debug("No work_dir in state for task %s", gid)
        return None

    project_dir_name = re.sub(r"[^a-zA-Z0-9\-]", "-", work_dir)
    claude_projects = Path.home() / ".claude" / "projects" / project_dir_name
    if not claude_projects.exists():
        logger.debug("Claude project dir not found: %s", claude_projects)
        return None

    jsonl_files = sorted(
        claude_projects.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if jsonl_files:
        return jsonl_files[0].stem
    return None


def _send_claude_commands(
    gid: str, session_name: str, task_name: str, task_url: str
) -> None:
    """Wait for run_task.sh setup to finish, then send claude + /mai via tmux send-keys."""
    marker = SCRIPT_DIR / "tmp" / f"setup_done_{gid}"

    for _ in range(900):  # max 15 min wait
        if marker.exists():
            break
        time.sleep(1)
    else:
        logger.error("Timeout waiting for setup of task %s", gid)
        return

    time.sleep(2)

    try:
        claude_launch = f"{CLAUDE_CMD} -n {shlex.quote(task_name)}"
        subprocess.run(
            ["tmux", "send-keys", "-t", session_name, "-l", claude_launch], check=True
        )
        subprocess.run(
            ["tmux", "send-keys", "-t", session_name, "Enter"], check=True
        )
        time.sleep(CLAUDE_STARTUP_WAIT)

        subprocess.run(
            ["tmux", "send-keys", "-t", session_name, "", "Enter"], check=True
        )
        time.sleep(1)
        subprocess.run(
            ["tmux", "send-keys", "-t", session_name, "", "Enter"], check=True
        )
        time.sleep(2)

        subprocess.run(
            ["tmux", "send-keys", "-t", session_name, "", "Enter"], check=True
        )
        time.sleep(1)

        mai_cmd = f"{CLAUDE_STARTUP_CMD} {task_url}"
        if CLAUDE_EXTRA_MSG:
            mai_cmd = f"{mai_cmd} {CLAUDE_EXTRA_MSG}"
        subprocess.run(
            ["tmux", "send-keys", "-t", session_name, "-l", mai_cmd], check=True
        )
        subprocess.run(
            ["tmux", "send-keys", "-t", session_name, "Enter"], check=True
        )

        logger.info("Claude + %s sent to task %s (%s)", CLAUDE_STARTUP_CMD, gid, task_url)

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
    # 前回のマーカーファイルが残っていたら削除（誤検知防止）
    marker = SCRIPT_DIR / "tmp" / f"setup_done_{gid}"
    if marker.exists():
        marker.unlink()
        logger.debug("Removed stale setup marker: %s", marker)

    session_name = f"task-{gid}"
    task_log = LOG_DIR / "tasks" / f"{gid}.log"

    task_log.parent.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Launching task %s (%s) in tmux session '%s'", gid, task_name, session_name
    )

    # Kill stale tmux session if it exists
    check = subprocess.run(
        ["tmux", "has-session", "-t", session_name], capture_output=True
    )
    if check.returncode == 0:
        logger.warning("tmux session '%s' already exists, killing it", session_name)
        subprocess.run(
            ["tmux", "kill-session", "-t", session_name], capture_output=True
        )

    cmd = [
        "tmux",
        "new-session",
        "-d",
        "-s",
        session_name,
        f"bash {RUN_TASK_SH} {gid}",
    ]
    env = os.environ.copy()
    env["TASK_LOG"] = str(task_log)

    try:
        subprocess.run(cmd, check=True, env=env, timeout=10)
        logger.info("tmux session started: tmux attach -t %s", session_name)

        repo_path = REPO_PATH
        dir_name = to_safe_dirname(task_name) if task_name else gid
        work_dir = os.path.join(repo_path, dir_name or gid)
        task_url = f"https://app.asana.com/0/0/{gid}/f"

        if "running_tasks" not in state:
            state["running_tasks"] = {}
        state["running_tasks"][gid] = {
            "name": task_name,
            "tmux_session": session_name,
            "work_dir": work_dir,
        }
        save_state(state)

        t = threading.Thread(
            target=_send_claude_commands,
            args=(gid, session_name, task_name, task_url),
            daemon=True,
        )
        t.start()
    except subprocess.CalledProcessError as exc:
        logger.error("Failed to create tmux session for task %s: %s", gid, exc)
    except subprocess.TimeoutExpired:
        logger.error("Timeout creating tmux session for task %s", gid)
