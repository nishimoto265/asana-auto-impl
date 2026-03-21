#!/bin/bash
# 実行中のタスクセッション一覧を表示する

REAL_PATH="$(readlink -f "$0" 2>/dev/null || readlink "$0" 2>/dev/null || echo "$0")"
SCRIPT_DIR="$(cd "$(dirname "$REAL_PATH")" && pwd)"
STATE_FILE="${SCRIPT_DIR}/tmp/state.json"

if [[ ! -f "$STATE_FILE" ]]; then
    echo "state.json が見つかりません"
    exit 1
fi

# running_tasks から一覧取得
TASKS=$(python3 -c "
import json, sys
with open('$STATE_FILE') as f:
    state = json.load(f)
tasks = state.get('running_tasks', {})
if not tasks:
    print('実行中のタスクはありません')
    sys.exit(0)
# ヘッダー
print(f'{\"タスク名\":<40} {\"アクセス方法\"}')
print('-' * 80)
for gid, info in tasks.items():
    name = info.get('name', gid)
    tmux = info.get('tmux_session', '')
    csid = info.get('claude_session', '')
    wdir = info.get('work_dir', '')
    print(f'{name:<40} tmux attach -t {tmux}')
    if csid and wdir:
        print(f'{\"\":<40} cd {wdir} && claude --resume {csid}')
    elif csid:
        print(f'{\"\":<40} claude --resume {csid}')
    else:
        print(f'{\"\":<40} (Claude session ID未取得)')
    print()
")

echo "$TASKS"
