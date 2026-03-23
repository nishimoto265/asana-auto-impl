#!/usr/bin/env bash
# run_task.sh – executed inside a tmux session "task-{gid}"
#
# Usage: run_task.sh <task_gid>
#
# Requires environment variables (loaded from .env by poll_asana.py or manually):
#   ASANA_PAT, REPO_PATH, CLAUDE_CMD
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
SHELL_CMD="${SHELL_CMD:-zsh -l}"
LOG_DIR="${LOG_DIR:-$SCRIPT_DIR/logs}"
TASK_LOG="${TASK_LOG:-$LOG_DIR/tasks/${GID}.log}"
CLONE_REPOS="${CLONE_REPOS:-}"
DEBUG_ZIP_PATH="${DEBUG_ZIP_PATH:-}"
DEBUG_ZIP_DEST="${DEBUG_ZIP_DEST:-}"

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

# Parse fields via dedicated helper script
read_field() {
    echo "$TASK_JSON" | python3 "$SCRIPT_DIR/lib/parse_task_json.py" "$1" 2>/dev/null || echo ""
}

TASK_NAME=$(read_field name)
TASK_NOTES=$(read_field notes)
TASK_URL=$(read_field permalink_url)

log "Task name: $TASK_NAME"
log "Task URL:  $TASK_URL"

# ---------------------------------------------------------------------------
# 2. Create workspace directory (uses shared Python logic for consistency)
# ---------------------------------------------------------------------------

if [[ -n "$TASK_NAME" ]]; then
    DIR_NAME=$(echo "$TASK_NAME" | PYTHONPATH="$SCRIPT_DIR" python3 -c "import sys; from lib.dirnames import to_safe_dirname; print(to_safe_dirname(sys.stdin.read().strip()))" 2>/dev/null || echo "$GID")
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

TEMPLATE_DIR="${REPO_PATH}/_template"

if [[ -z "$CLONE_REPOS" ]]; then
    log "CLONE_REPOS is empty, skipping clone/template processing."
elif [[ -d "$TEMPLATE_DIR" ]]; then
    # CLONE_REPOSからリポジトリ名を抽出
    IFS=',' read -ra REPOS <<< "$CLONE_REPOS"
    REPO_NAMES=()
    for repo in "${REPOS[@]}"; do
        repo=$(echo "$repo" | xargs)
        repo_name=$(basename "$repo" .git)
        REPO_NAMES+=("$repo_name")
    done

    # テンプレートにないリポジトリはcloneしておく
    for i in "${!REPOS[@]}"; do
        repo=$(echo "${REPOS[$i]}" | xargs)
        repo_name="${REPO_NAMES[$i]}"
        if [[ ! -d "$TEMPLATE_DIR/$repo_name" ]]; then
            log "Template missing $repo_name, cloning..."
            (cd "$TEMPLATE_DIR" && git clone "$repo" 2>&1) || log "WARNING: clone failed for $repo"
        fi
    done

    # テンプレートを git pull + npm install で最新化
    log "Updating template repositories..."
    for repo_name in "${REPO_NAMES[@]}"; do
        if [[ -d "$TEMPLATE_DIR/$repo_name/.git" ]]; then
            (cd "$TEMPLATE_DIR/$repo_name" && git pull 2>&1) || log "WARNING: git pull failed for $repo_name"
            log "Updated $repo_name"
        fi
    done
    log "Template update complete."

    # package.jsonがあるリポジトリだけnpm install
    for repo_name in "${REPO_NAMES[@]}"; do
        if [[ -f "$TEMPLATE_DIR/$repo_name/package.json" ]]; then
            log "npm install in template/$repo_name..."
            (cd "$TEMPLATE_DIR/$repo_name" && npm install 2>&1) || log "WARNING: npm install failed for $repo_name"
        fi
    done

    # CLONE_REPOSに該当するものだけコピー
    log "Copying from template: $TEMPLATE_DIR"
    for repo_name in "${REPO_NAMES[@]}"; do
        if [[ -d "$TEMPLATE_DIR/$repo_name" && ! -d "$WORK_DIR/$repo_name" ]]; then
            cp -r "$TEMPLATE_DIR/$repo_name" "$WORK_DIR/$repo_name"
            log "Copied $repo_name"
        elif [[ -d "$WORK_DIR/$repo_name" ]]; then
            log "Already exists: $repo_name, skipping"
        else
            log "WARNING: $repo_name not found in template"
        fi
    done
    log "Template copy complete."
else
    log "No template dir found, falling back to git clone..."
    (
        cd "$WORK_DIR"
        IFS=',' read -ra REPOS <<< "$CLONE_REPOS"
        PIDS=()
        for repo in "${REPOS[@]}"; do
            repo=$(echo "$repo" | xargs)
            git clone "$repo" 2>&1 &
            PIDS+=($!)
        done

        CLONE_FAILED=0
        for i in "${!PIDS[@]}"; do
            wait ${PIDS[$i]} || { log "WARNING: clone failed for ${REPOS[$i]}"; CLONE_FAILED=1; }
        done

        if [[ "$CLONE_FAILED" -eq 1 ]]; then
            log "WARNING: One or more clone operations failed"
        fi
    ) || true
    log "Clone complete."

    log "Installing npm dependencies..."
    (
        cd "$WORK_DIR"
        IFS=',' read -ra REPOS2 <<< "$CLONE_REPOS"
        PIDS=()
        for repo in "${REPOS2[@]}"; do
            repo=$(echo "$repo" | xargs)
            dir=$(basename "$repo" .git)
            if [[ -f "$dir/package.json" ]]; then
                (cd "$dir" && npm install 2>&1) &
                PIDS+=($!)
            fi
        done

        NPM_FAILED=0
        for pid in "${PIDS[@]}"; do
            wait $pid || { NPM_FAILED=1; }
        done

        if [[ "$NPM_FAILED" -eq 1 ]]; then
            log "WARNING: One or more npm install operations failed"
        fi
    ) || true
    log "npm install complete."
fi

# Extract debug.zip if present
if [[ -n "$DEBUG_ZIP_PATH" ]]; then
    DEBUG_ZIP_PATH="${DEBUG_ZIP_PATH/#\~/$HOME}"
    if [[ -f "$DEBUG_ZIP_PATH" ]]; then
        log "Extracting $(basename "$DEBUG_ZIP_PATH") into $DEBUG_ZIP_DEST/"
        unzip -o "$DEBUG_ZIP_PATH" -d "$WORK_DIR/$DEBUG_ZIP_DEST/" 2>&1 | tee -a "$TASK_LOG"
    else
        log "WARNING: $DEBUG_ZIP_PATH not found – skipping extraction."
    fi
fi

# ---------------------------------------------------------------------------
# 4. Signal setup complete and hand over to interactive shell
# ---------------------------------------------------------------------------

# Write marker file so poller knows setup is done
mkdir -p "${SCRIPT_DIR}/tmp"
touch "${SCRIPT_DIR}/tmp/setup_done_${GID}"

log "Setup complete. Handing over to interactive shell."
log "  Access session: tmux attach -t task-${GID}"

# Replace with an interactive shell in WORK_DIR so tmux session stays alive
# The poller will send claude + /mai commands via tmux send-keys
cd "$WORK_DIR"
exec $SHELL_CMD
