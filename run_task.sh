#!/usr/bin/env bash
# run_task.sh – executed inside a tmux session "task-{gid}"
#
# Usage: run_task.sh <task_gid>
#
# Requires environment variables (loaded from .env by poll_asana.py or manually):
#   ASANA_PAT, REPO_PATH, CLAUDE_CMD, CLAUDE_MAX_TURNS, CLAUDE_MAX_BUDGET_USD
#
# Optional:
#   TASK_LOG – path to log file (defaults to ./logs/tasks/<gid>.log)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load .env if present
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.env"
    set +a
fi

# ---------------------------------------------------------------------------
# Args & defaults
# ---------------------------------------------------------------------------

GID="${1:?Usage: run_task.sh <task_gid>}"

REPO_PATH="${REPO_PATH:-$HOME/project}"
REPO_PATH="${REPO_PATH/#\~/$HOME}"
CLAUDE_CMD="${CLAUDE_CMD:-claude}"
CLAUDE_MAX_TURNS="${CLAUDE_MAX_TURNS:-20}"
CLAUDE_MAX_BUDGET_USD="${CLAUDE_MAX_BUDGET_USD:-5}"
LOG_DIR="${LOG_DIR:-$SCRIPT_DIR/logs}"
TASK_LOG="${TASK_LOG:-$LOG_DIR/tasks/${GID}.log}"

mkdir -p "$(dirname "$TASK_LOG")"

# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

log() {
    local msg
    msg="$(date '+%Y-%m-%d %H:%M:%S') [run_task] $*"
    echo "$msg" | tee -a "$TASK_LOG"
}

# ---------------------------------------------------------------------------
# 1. Fetch task details from Asana API
# ---------------------------------------------------------------------------

log "Fetching task details for GID=$GID"

TASK_JSON=$(curl -sf \
    -H "Authorization: Bearer $ASANA_PAT" \
    "https://app.asana.com/api/1.0/tasks/${GID}?opt_fields=gid,name,notes,permalink_url" \
) || {
    log "ERROR: Failed to fetch task details from Asana API"
    exit 1
}

TASK_NAME=$(echo "$TASK_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['name'])" 2>/dev/null || echo "")
TASK_NOTES=$(echo "$TASK_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['data'].get('notes',''))" 2>/dev/null || echo "")
TASK_URL=$(echo "$TASK_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['data'].get('permalink_url',''))" 2>/dev/null || echo "")

log "Task name: $TASK_NAME"
log "Task URL:  $TASK_URL"

# ---------------------------------------------------------------------------
# 2. Create workspace directory
# ---------------------------------------------------------------------------

to_safe_dirname() {
    # ファイルシステムNGな文字だけ置換。日本語はそのまま残す
    echo "$1" | sed 's/[/:*?"<>|\\]/-/g' | sed 's/  */-/g' | sed 's/--*/-/g' | sed 's/^-//;s/-$//'
}

if [[ -n "$TASK_NAME" ]]; then
    DIR_NAME=$(to_safe_dirname "$TASK_NAME")
else
    DIR_NAME="$GID"
fi

# Fallback if result is empty
[[ -z "$DIR_NAME" ]] && DIR_NAME="$GID"

WORK_DIR="${REPO_PATH}/${DIR_NAME}"
log "Creating workspace: $WORK_DIR"
mkdir -p "$WORK_DIR"

# ---------------------------------------------------------------------------
# 3. Clone repos & install dependencies
# ---------------------------------------------------------------------------

log "Cloning repositories..."
set +e
(
    cd "$WORK_DIR"
    git clone https://github.com/everytv/delish-server 2>&1 &
    PID_SERVER=$!
    git clone https://github.com/everytv/delish-web2 2>&1 &
    PID_WEB=$!
    git clone https://github.com/everytv/delish-dashboard2 2>&1 &
    PID_DASH=$!

    CLONE_FAILED=0
    wait ${PID_SERVER} || { log "WARNING: delish-server clone failed"; CLONE_FAILED=1; }
    wait ${PID_WEB}    || { log "WARNING: delish-web2 clone failed"; CLONE_FAILED=1; }
    wait ${PID_DASH}   || { log "WARNING: delish-dashboard2 clone failed"; CLONE_FAILED=1; }

    if [[ "$CLONE_FAILED" -eq 1 ]]; then
        log "WARNING: One or more clone operations failed"
    fi
)
set -e
log "Clone complete."

log "Installing npm dependencies..."
set +e
(
    cd "$WORK_DIR"
    (cd delish-web2 && npm install 2>&1) &
    PID_NPM_WEB=$!
    (cd delish-dashboard2 && npm install 2>&1) &
    PID_NPM_DASH=$!

    NPM_FAILED=0
    wait ${PID_NPM_WEB}  || { log "WARNING: delish-web2 npm install failed"; NPM_FAILED=1; }
    wait ${PID_NPM_DASH}  || { log "WARNING: delish-dashboard2 npm install failed"; NPM_FAILED=1; }

    if [[ "$NPM_FAILED" -eq 1 ]]; then
        log "WARNING: One or more npm install operations failed"
    fi
)
set -e
log "npm install complete."

# Extract debug.zip if present
if [[ -f "$HOME/Downloads/debug.zip" ]]; then
    log "Extracting debug.zip into delish-server/"
    unzip -o "$HOME/Downloads/debug.zip" -d "$WORK_DIR/delish-server/" 2>&1 | tee -a "$TASK_LOG"
else
    log "WARNING: ~/Downloads/debug.zip not found – skipping extraction."
fi

# ---------------------------------------------------------------------------
# 4. Signal setup complete and hand over to interactive shell
# ---------------------------------------------------------------------------

# Write marker file so poller knows setup is done
touch "${SCRIPT_DIR}/tmp/setup_done_${GID}"

log "Setup complete. Handing over to interactive shell."
log "  Access session: tmux attach -t task-${GID}"

# Replace with an interactive shell in WORK_DIR so tmux session stays alive
# The poller will send claude + /mai commands via tmux send-keys
cd "$WORK_DIR"
exec zsh -l
