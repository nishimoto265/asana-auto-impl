#!/usr/bin/env python3
"""Print running task sessions from state.json.

Usage: python3 -m lib.list_sessions <state_file>
"""

import json
import subprocess
import sys


def _tmux_session_alive(session_name: str) -> bool:
    """Check if a tmux session exists."""
    result = subprocess.run(
        ["tmux", "has-session", "-t", session_name],
        capture_output=True,
    )
    return result.returncode == 0


def main() -> None:
    state_file = sys.argv[1] if len(sys.argv) > 1 else ""
    if not state_file:
        print("Usage: list_sessions.py <state_file>", file=sys.stderr)
        sys.exit(1)

    with open(state_file) as f:
        state = json.load(f)

    tasks = state.get("running_tasks", {})
    if not tasks:
        print("実行中のタスクはありません")
        return

    print(f'{"タスク名":<40} {"状態":<8} {"アクセス方法"}')
    print("-" * 90)
    for gid, info in tasks.items():
        name = info.get("name", gid)
        tmux = info.get("tmux_session", "")
        csid = info.get("claude_session", "")
        wdir = info.get("work_dir", "")
        alive = _tmux_session_alive(tmux) if tmux else False
        status = "稼働中" if alive else "終了"

        if alive:
            print(f"{name:<40} {status:<8} tmux attach -t {tmux}")
        else:
            print(f"{name:<40} {status:<8} (tmuxセッション終了)")
        if csid and wdir:
            print(f'{"":<40} {"":8} cd {wdir} && claude --resume {csid}')
        elif csid:
            print(f'{"":<40} {"":8} claude --resume {csid}')
        else:
            print(f'{"":<40} {"":8} (Claude session ID未取得)')
        print()


if __name__ == "__main__":
    main()
