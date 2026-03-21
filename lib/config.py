"""Environment configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ASANA_PAT: str = os.environ.get("ASANA_PAT", "")
ASANA_WORKSPACE_GID: str = os.environ.get("ASANA_WORKSPACE_GID", "")
ASANA_PROJECT_GID: str = os.environ.get("ASANA_PROJECT_GID", "")
POLL_INTERVAL: int = int(os.environ.get("ASANA_POLL_INTERVAL_SEC", "60"))
LOG_DIR: Path = Path(os.environ.get("LOG_DIR", "./logs")).resolve()
STATE_FILE: Path = Path(os.environ.get("TMP_DIR", "./tmp")).resolve() / "state.json"

SCRIPT_DIR: Path = Path(__file__).resolve().parent.parent
RUN_TASK_SH: Path = SCRIPT_DIR / "run_task.sh"

ASANA_BASE_URL: str = "https://app.asana.com/api/1.0"
