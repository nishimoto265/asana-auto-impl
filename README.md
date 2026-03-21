# Asana Auto Implementation

Asanaで自分に割り当てられた新規タスクを自動検知し、Claude Codeを起動して `/mai` で実装を開始するシステム。

## 前提条件

- Python 3.10+
- tmux
- git
- Node.js / npm
- Claude Code CLI (`claude`)
- Asana Personal Access Token

## セットアップ

```bash
# 依存パッケージのインストール
pip install -r requirements.txt

# 環境変数の設定
cp .env.example .env
# .env を編集して ASANA_PAT と ASANA_WORKSPACE_GID を設定
```

### .env の設定項目

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `ASANA_PAT` | Asana Personal Access Token（必須） | - |
| `ASANA_WORKSPACE_GID` | 対象ワークスペースのGID（必須） | - |
| `ASANA_POLL_INTERVAL_SEC` | ポーリング間隔（秒） | `60` |
| `REPO_PATH` | ワークスペース作成先 | `~/project` |
| `CLAUDE_CMD` | Claude CLIコマンド | `claude` |
| `LOG_DIR` | ログ出力先 | `./logs` |
| `TMP_DIR` | 一時ファイル置き場 | `./tmp` |

## プロジェクト構成

```
poll_asana.py          # エントリポイント（ポーリングループ）
run_task.sh            # タスクごとのセットアップスクリプト
list_sessions.sh       # 実行中セッション一覧表示
test_claude_launch.sh  # Claude起動テスト用
requirements.txt
.env.example
lib/
  config.py            # 環境変数・定数の定義
  logging_setup.py     # ロガーの初期化
  state.py             # state.json の読み書き
  asana_api.py         # Asana APIクライアント
  launcher.py          # tmuxセッション起動・Claude送信
  dirnames.py          # ディレクトリ名サニタイズ（Python/Shell共用）
  parse_task_json.py   # run_task.sh 用JSONパーサ
  list_sessions.py     # list_sessions.sh 用表示ロジック
```

## 起動方法

tmuxセッション `asana-poller` 内で起動する:

```bash
tmux new-session -d -s asana-poller "python3 poll_asana.py"
tmux attach -t asana-poller
```

## 動作の流れ

1. `poll_asana.py` が `ASANA_POLL_INTERVAL_SEC` 秒ごとにAsana APIをポーリング
2. 自分に割り当てられた未完了タスク一覧を取得
3. `state.json` と比較して新規タスクを検出
4. 新規タスクごとに `tmux new-session -d -s task-{gid}` でセッション作成
5. `run_task.sh` がセッション内で以下を実行:
   - Asana APIからタスク詳細取得
   - `~/project/{task-name}/` ディレクトリ作成
   - 3つのリポジトリをclone & npm install
   - Claude Codeを起動し `/mai` でタスク情報を送信

## タスクセッションへの接続

```bash
# 実行中のセッション一覧
./list_sessions.sh

# 特定タスクに接続
tmux attach -t task-{gid}
```

## ログ

- `logs/poller.log` — ポーリング状況
- `logs/tasks/{gid}.log` — タスク別実行ログ

## 状態管理

`tmp/state.json` でタスクの処理状態を管理:

```json
{
  "known_task_gids": [],
  "running_tasks": {},
  "completed_task_gids": []
}
```

状態ファイルが破損した場合は自動的に初期化される。

## トラブルシューティング

### ポーラーが起動しない
- `.env` に `ASANA_PAT` と `ASANA_WORKSPACE_GID` が設定されているか確認
- `pip install -r requirements.txt` を実行済みか確認

### タスクが検知されない
- `logs/poller.log` を確認
- Asana上でタスクが自分にアサインされているか確認
- ワークスペースGIDが正しいか確認

### 初回起動時に既存タスクが全て起動される
初回起動時は既存タスクを `known_task_gids` に登録するため、起動されない。
初回起動後に新しくアサインされたタスクのみが対象となる。
