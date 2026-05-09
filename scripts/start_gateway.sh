#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:-foreground}"

if [[ -f "${DIR}/.env" ]]; then
  # shellcheck disable=SC1090
  source "${DIR}/.env"
fi

# shellcheck source=/dev/null
source "${SCRIPT_DIR}/runtime_paths.sh"

export PYTHONPATH="${DIR}:${PYTHONPATH:-}"

PID_FILE="${VLLM_CLAUDE_RUN_DIR}/gateway.pid"
LOG_FILE="${VLLM_CLAUDE_LOG_DIR}/gateway.log"

if [[ -x "/home/heshan/.conda/envs/paper2any/bin/python" ]]; then
  PYTHON_BIN="/home/heshan/.conda/envs/paper2any/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  PYTHON_BIN="$(command -v python)"
fi

if [[ "$MODE" == "--daemon" ]]; then
  if [[ -f "$PID_FILE" ]]; then
    existing_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
      echo "Gateway is already running (pid=${existing_pid})."
      exit 0
    fi
    rm -f "$PID_FILE"
  fi

  nohup "$PYTHON_BIN" -m llmnode >>"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  echo "Gateway started (pid=$(cat "$PID_FILE"))."
  echo "Log file: $LOG_FILE"
  exit 0
fi

exec "$PYTHON_BIN" -m llmnode
