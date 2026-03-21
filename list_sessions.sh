#!/bin/bash
# 実行中のタスクセッション一覧を表示する

REAL_PATH="$(readlink -f "$0" 2>/dev/null || readlink "$0" 2>/dev/null || echo "$0")"
SCRIPT_DIR="$(cd "$(dirname "$REAL_PATH")" && pwd)"
STATE_FILE="${SCRIPT_DIR}/tmp/state.json"

if [[ ! -f "$STATE_FILE" ]]; then
    echo "state.json が見つかりません"
    exit 1
fi

python3 "$SCRIPT_DIR/lib/list_sessions.py" "$STATE_FILE"
