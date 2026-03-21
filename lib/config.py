"""Environment configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ASANA_PAT: str = os.environ.get("ASANA_PAT", "")
ASANA_WORKSPACE_GID: str = os.environ.get("ASANA_WORKSPACE_GID", "")
ASANA_PROJECT_GID: str = os.environ.get("ASANA_PROJECT_GID", "")
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
    os.environ.get("CLONE_REPOS", "https://github.com/everytv/delish-server,https://github.com/everytv/delish-web2,https://github.com/everytv/delish-dashboard2").split(",")
]
# npm install対象ディレクトリ（カンマ区切り）
NPM_INSTALL_DIRS: list[str] = [
    d.strip() for d in
    os.environ.get("NPM_INSTALL_DIRS", "delish-web2,delish-dashboard2").split(",")
]
# debug.zip
DEBUG_ZIP_PATH: str = os.path.expanduser(os.environ.get("DEBUG_ZIP_PATH", "~/Downloads/debug.zip"))
DEBUG_ZIP_DEST: str = os.environ.get("DEBUG_ZIP_DEST", "delish-server")

# Claude起動設定
CLAUDE_STARTUP_CMD: str = os.environ.get("CLAUDE_STARTUP_CMD", "/mai")  # Claude起動後に送るコマンド
CLAUDE_STARTUP_WAIT: int = int(os.environ.get("CLAUDE_STARTUP_WAIT", "8"))  # Claude起動待ち秒数
SHELL_CMD: str = os.environ.get("SHELL_CMD", "zsh -l")  # tmuxセッション内のシェル
