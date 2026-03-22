# Asana Auto Implementation

Asanaで自分に割り当てられた新規タスクを自動検知し、リポジトリのclone・セットアップ・Claude Code起動までを自動で行うシステム。

ローカルポーリング方式。公開サーバー不要。

## クイックスタート

```bash
# 1. 依存インストール
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. 環境変数設定
cp .env.example .env
# .env を編集（ASANA_PAT, ASANA_WORKSPACE_GID は必須）

# 3. 起動
asana-start
```

## 前提条件

- Python 3.10+
- tmux
- git / Node.js / npm
- Claude Code CLI
- Asana Personal Access Token（https://app.asana.com/0/my-apps で発行）

## 初期設定

### .env

| 変数 | 必須 | 説明 | デフォルト |
|------|------|------|-----------|
| `ASANA_PAT` | ○ | Personal Access Token | - |
| `ASANA_WORKSPACE_GID` | ○ | ワークスペースGID | - |
| `ASANA_PROJECT_GID` | | 監視対象プロジェクト（未設定でワークスペース全体） | - |
| `ASANA_POLL_INTERVAL_SEC` | | ポーリング間隔（秒） | `10` |
| `REPO_PATH` | | プロジェクト作成先 | `~/project` |
| `CLAUDE_CMD` | | Claude CLIパス | `claude` |
| `CLONE_REPOS` | | clone対象リポジトリ（カンマ区切り） | delish 3リポ |
| `NPM_INSTALL_DIRS` | | npm install対象（カンマ区切り） | `delish-web2,delish-dashboard2` |
| `DEBUG_ZIP_PATH` | | 展開するzipファイルのパス | `~/Downloads/debug.zip` |
| `DEBUG_ZIP_DEST` | | zip展開先ディレクトリ | `delish-server` |
| `CLAUDE_STARTUP_CMD` | | Claude起動後に送るコマンド | `/mai` |
| `CLAUDE_STARTUP_WAIT` | | Claude起動待ち秒数 | `8` |
| `SHELL_CMD` | | tmuxセッション内のシェル | `"zsh -l"` |
| `LOG_DIR` | | ログ出力先 | `./logs` |
| `TMP_DIR` | | 一時ファイル置き場 | `./tmp` |

### コマンド

インストール時に `~/.local/bin/` にコマンドが配置される。

```bash
asana-start   # poller起動
asana-list    # 実行中セッション一覧
asana-clean   # 全停止 + state削除
```

## 動作の流れ

1. `poll_asana.py` が一定間隔でAsana APIをポーリング
2. 自分に割り当てられた未完了タスクの新規追加を検知
3. タスクごとにtmuxセッションを作成し `run_task.sh` を実行
4. `run_task.sh` がリポジトリのclone・npm install・debug.zip展開を行う
5. セットアップ完了後、Claude Codeを起動し指定コマンド（デフォルト `/mai`）+ AsanaタスクURLを送信
6. Claude session IDを自動取得し `state.json` に記録

```
[poller] ─検知→ [tmux: task-{gid}] ─setup→ [Claude Code + /mai]
                                     ↑
                              asana-list で一覧表示
```

## セッション操作

```bash
# 一覧（稼働中/終了の状態付き）
asana-list

# tmuxセッションに接続
tmux attach -t task-{gid}

# tmux内でのセッション切り替え
tmux switch-client -t task-{gid}

# Claudeセッション再開（tmux終了後）
cd ~/project/{task-name} && claude --resume {session-id}

# tmux内スクロール: Ctrl+B → [ → 上下キー → q で抜ける
```

## プロジェクト構成

```
poll_asana.py          # エントリポイント
run_task.sh            # タスク別セットアップ
list_sessions.sh       # セッション一覧
test_claude_launch.sh  # Claude起動テスト用
lib/
  config.py            # 環境変数・定数
  asana_api.py         # Asana APIクライアント
  state.py             # state.json管理
  launcher.py          # tmux起動・Claude送信
  dirnames.py          # ディレクトリ名サニタイズ
  logging_setup.py     # ロガー初期化
  parse_task_json.py   # JSON解析ヘルパー
  list_sessions.py     # 一覧表示ロジック
```

## トラブルシューティング

| 症状 | 対処 |
|------|------|
| poller起動しない | `.env` の `ASANA_PAT` と `ASANA_WORKSPACE_GID` を確認 |
| タスクが検知されない | `logs/poller.log` を確認。`ASANA_PROJECT_GID` の設定を確認 |
| tmuxセッションがすぐ終了する | `logs/tasks/{gid}.log` を確認。`.env` のクオート（`SHELL_CMD="zsh -l"`）を確認 |
| Claude起動が `--print` モードエラー | パイプ経由でstdinが奪われていないか確認 |
| 二重起動エラー | `asana-clean` で全停止してから再起動 |
| 古いセッションが残る | `asana-clean` または `tmux kill-server` |
