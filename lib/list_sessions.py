#!/usr/bin/env python3
"""Print running task sessions from state.json.

Usage: python3 -m lib.list_sessions <state_file>
"""

import json
import sys


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

    print(f'{"タスク名":<40} {"アクセス方法"}')
    print("-" * 80)
    for gid, info in tasks.items():
        name = info.get("name", gid)
        tmux = info.get("tmux_session", "")
        csid = info.get("claude_session", "")
        wdir = info.get("work_dir", "")
        print(f"{name:<40} tmux attach -t {tmux}")
        if csid and wdir:
            print(f'{"":<40} cd {wdir} && claude --resume {csid}')
        elif csid:
            print(f'{"":<40} claude --resume {csid}')
        else:
            print(f'{"":<40} (Claude session ID未取得)')
        print()


if __name__ == "__main__":
    main()
