#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/runtime_paths.sh"

PID_FILE="${VLLM_CLAUDE_RUN_DIR}/agent.pid"

stop_pid() {
  local pid="$1"

  if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
    return 1
  fi

  kill "$pid" 2>/dev/null || true
  for _ in {1..30}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
    sleep 1
  done

  kill -9 "$pid" 2>/dev/null || true
  return 0
}

stopped=false

if [[ -f "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if stop_pid "$pid"; then
    echo "Agent stopped (pid=${pid})."
    stopped=true
  fi
  rm -f "$PID_FILE"
fi

if [[ "$stopped" == false ]]; then
  legacy_pid="$(pgrep -f "python(3)? -m llmnode\\.agent$" | head -n 1 || true)"
  if [[ -n "$legacy_pid" ]]; then
    stop_pid "$legacy_pid" || true
    echo "Agent stopped via legacy process match (pid=${legacy_pid})."
    stopped=true
  fi
fi

if [[ "$stopped" == false ]]; then
  echo "Agent is not running."
fi
