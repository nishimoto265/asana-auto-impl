"""Environment configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ASANA_PAT: str = os.environ.get("ASANA_PAT", "")
ASANA_WORKSPACE_GID: str = os.environ.get("ASANA_WORKSPACE_GID", "")
ASANA_PROJECT_GIDS: list[str] = [
    g.strip() for g in
    os.environ.get("ASANA_PROJECT_GIDS", os.environ.get("ASANA_PROJECT_GID", "")).split(",") if g.strip()
]
POLL_INTERVAL: int = int(os.environ.get("ASANA_POLL_INTERVAL_SEC", "10"))
LOG_DIR: Path = Path(os.environ.get("LOG_DIR", "./logs")).resolve()
STATE_FILE: Path = Path(os.environ.get("TMP_DIR", "./tmp")).resolve() / "state.json"

SCRIPT_DIR: Path = Path(__file__).resolve().parent.parent
RUN_TASK_SH: Path = SCRIPT_DIR / "run_task.sh"

ASANA_BASE_URL: str = "https://app.asana.com/api/1.0"

REPO_PATH: str = os.path.expanduser(os.environ.get("REPO_PATH", "~/project"))
CLAUDE_CMD: str = os.environ.get("CLAUDE_CMD", "claude")

# Clone対象リポジトリ（カンマ区切り）
CLONE_REPOS: list[str] = [
    r.strip() for r in
    os.environ.get("CLONE_REPOS", "").split(",") if r.strip()
]
# サブタスク監視対象の親タスクGID（カンマ区切り）
WATCH_PARENT_TASKS: list[str] = [
    g.strip() for g in
    os.environ.get("ASANA_WATCH_PARENT_TASKS", "").split(",") if g.strip()
]
# debug.zip
DEBUG_ZIP_PATH: str = os.path.expanduser(os.environ.get("DEBUG_ZIP_PATH", ""))
DEBUG_ZIP_DEST: str = os.environ.get("DEBUG_ZIP_DEST", "")

# Claude起動設定
CLAUDE_STARTUP_CMD: str = os.environ.get("CLAUDE_STARTUP_CMD", "/mai")  # Claude起動後に送るコマンド
CLAUDE_STARTUP_WAIT: int = int(os.environ.get("CLAUDE_STARTUP_WAIT", "8"))  # Claude起動待ち秒数
SHELL_CMD: str = os.environ.get("SHELL_CMD", "zsh -l")  # tmuxセッション内のシェル
