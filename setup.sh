#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="$HOME/.local/bin"

echo "=== asana-auto-impl セットアップ ==="

# 1. venv + 依存インストール
if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
    echo "[1/4] venv作成 + 依存インストール..."
    python3 -m venv "$SCRIPT_DIR/.venv"
else
    echo "[1/4] venv既存、依存のみ更新..."
fi
source "$SCRIPT_DIR/.venv/bin/activate"
pip install -q -r "$SCRIPT_DIR/requirements.txt"

# 2. .env
if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    echo "[2/4] .env を作成しました。編集してください: $SCRIPT_DIR/.env"
else
    echo "[2/4] .env既存、スキップ"
fi

# 3. コマンド登録
mkdir -p "$BIN_DIR"

cat > "$BIN_DIR/asana-start" << EOF
#!/bin/bash
cd "$SCRIPT_DIR" && source .venv/bin/activate && python3 poll_asana.py
EOF

cat > "$BIN_DIR/asana-clean" << EOF
#!/bin/bash
pkill -f poll_asana 2>/dev/null
tmux kill-server 2>/dev/null
rm -f "$SCRIPT_DIR/tmp/"*
echo "poller停止・tmux全終了・state削除 完了"
EOF

ln -sf "$SCRIPT_DIR/list_sessions.sh" "$BIN_DIR/asana-list"
chmod +x "$BIN_DIR/asana-start" "$BIN_DIR/asana-clean"
echo "[3/4] コマンド登録: asana-start / asana-list / asana-clean"

# 4. PATH確認
SHELL_RC="$HOME/.zshrc"
[[ "$SHELL" == */bash ]] && SHELL_RC="$HOME/.bashrc"
if ! echo "$PATH" | grep -q "$BIN_DIR"; then
    # rcファイルに既に追記済みでないか確認（重複防止）
    if ! grep -qF "$BIN_DIR" "$SHELL_RC" 2>/dev/null; then
        echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$SHELL_RC"
        echo "[4/4] PATHに $BIN_DIR を追加しました（$SHELL_RC）。ターミナルを再起動してください"
    else
        echo "[4/4] PATH設定済み（$SHELL_RC に記載あり）"
    fi
else
    echo "[4/4] PATH設定済み"
fi

echo ""
echo "=== セットアップ完了 ==="
echo "1. .env を編集: $SCRIPT_DIR/.env"
echo "2. 起動: asana-start（初回起動時にテンプレートが自動作成されます）"
