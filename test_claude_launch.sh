#!/bin/bash
# tmux send-keys でclaude起動 → /mai送信をテストするスクリプト
# 既存のディレクトリを使い、cloneはスキップする

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/.env" 2>/dev/null || true

WORK_DIR="${1:-$HOME/project/テスト5-フルフロー}"
GID="test-$(date +%s)"
SESSION_NAME="task-${GID}"
CLAUDE_CMD="${CLAUDE_CMD:-claude}"

echo "=== Claude Launch Test ==="
echo "Work dir: $WORK_DIR"
echo "Session:  $SESSION_NAME"

if [[ ! -d "$WORK_DIR" ]]; then
    echo "ERROR: $WORK_DIR does not exist. Specify an existing project dir."
    exit 1
fi

# 1. tmuxセッション作成（bashで待機）
tmux new-session -d -s "$SESSION_NAME" "cd '$WORK_DIR' && exec zsh -l"
sleep 1
echo "[OK] tmux session created"

# 2. claude起動
tmux send-keys -t "$SESSION_NAME" "$CLAUDE_CMD" Enter
echo "[..] Waiting for Claude to start (8s)..."
sleep 8

# 3. Enter×2（初期プロンプト通過）
tmux send-keys -t "$SESSION_NAME" "" Enter
sleep 1
tmux send-keys -t "$SESSION_NAME" "" Enter
sleep 2

# 4. bypass permission
tmux send-keys -t "$SESSION_NAME" "" Enter
sleep 1

# 5. /mai送信
tmux send-keys -t "$SESSION_NAME" "/mai" Enter
sleep 2

# 6. タスク情報送信
TASK_INFO="テスト用タスク情報
タイトル: テストタスク
説明: これはClaude起動テストです"

echo "$TASK_INFO" | tmux load-buffer -
tmux paste-buffer -t "$SESSION_NAME"
sleep 1
tmux send-keys -t "$SESSION_NAME" "" Enter

echo ""
echo "=== Done ==="
echo "Attach: tmux attach -t $SESSION_NAME"
echo ""
echo "Check pane content:"
echo "  tmux capture-pane -t $SESSION_NAME -p | tail -20"
