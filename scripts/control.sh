#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -f "${PROJECT_DIR}/.env" ]]; then
  # shellcheck disable=SC1090
  source "${PROJECT_DIR}/.env"
fi

# shellcheck source=/dev/null
source "${SCRIPT_DIR}/runtime_paths.sh"

ACTION="${1:-status}"
GATEWAY_PID_FILE="${VLLM_CLAUDE_RUN_DIR}/gateway.pid"
AGENT_PID_FILE="${VLLM_CLAUDE_RUN_DIR}/agent.pid"
WEB_PID_FILE="${VLLM_CLAUDE_RUN_DIR}/web-console.pid"
GATEWAY_URL="${VLLM_CLAUDE_GATEWAY_BASE_URL:-http://127.0.0.1:4000}"
AGENT_URL="${VLLM_CLAUDE_AGENT_BASE_URL:-http://127.0.0.1:4010}"
MODEL_DIR="${VLLM_CLAUDE_VLLM_MODEL_DIR:-${PROJECT_DIR}/models/Qwen/Qwen3.6-35B-A3B-FP8}"
WEB_CONSOLE_DIR="${VLLM_CLAUDE_WEB_CONSOLE_DIR:-${PROJECT_DIR}/web-console}"
WEB_CONSOLE_PORT="${VLLM_CLAUDE_WEB_CONSOLE_PORT:-5173}"
WEB_CONSOLE_URL="${VLLM_CLAUDE_WEB_CONSOLE_URL:-http://127.0.0.1:${WEB_CONSOLE_PORT}}"
WEB_CONSOLE_LOG_FILE="${VLLM_CLAUDE_LOG_DIR}/web-console.log"
START_CLEANUP_NEEDED=0

is_pid_running() {
  local pid_file="$1"

  if [[ ! -f "$pid_file" ]]; then
    return 1
  fi

  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

pid_from_file() {
  local pid_file="$1"

  if [[ ! -f "$pid_file" ]]; then
    return 1
  fi

  cat "$pid_file" 2>/dev/null || true
}

probe_process_state() {
  local pid_file="$1"
  local port="${2:-}"
  local url="${3:-}"

  local pid=""
  local pid_running=false
  local port_listening=false
  local http_ready=false

  pid="$(pid_from_file "$pid_file" || true)"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    pid_running=true
  fi

  if [[ -n "$port" ]] && port_in_use "$port"; then
    port_listening=true
  fi

  if [[ -n "$url" ]] && http_ok "$url"; then
    http_ready=true
  fi

  local state="stopped"
  if [[ "$http_ready" == true ]]; then
    state="ready"
  elif [[ "$pid_running" == true || "$port_listening" == true ]]; then
    state="partial"
  fi

  printf 'pid=%s\n' "$pid"
  printf 'pid_running=%s\n' "$pid_running"
  printf 'port_listening=%s\n' "$port_listening"
  printf 'http_ready=%s\n' "$http_ready"
  printf 'state=%s\n' "$state"
}

print_process_status() {
  local name="$1"
  local pid_file="$2"
  local port="${3:-}"
  local url="${4:-}"
  local probe

  probe="$(probe_process_state "$pid_file" "$port" "$url")"
  local pid
  local pid_running
  local port_listening
  local http_ready
  local state
  pid="$(printf '%s\n' "$probe" | sed -n 's/^pid=//p')"
  pid_running="$(printf '%s\n' "$probe" | sed -n 's/^pid_running=//p')"
  port_listening="$(printf '%s\n' "$probe" | sed -n 's/^port_listening=//p')"
  http_ready="$(printf '%s\n' "$probe" | sed -n 's/^http_ready=//p')"
  state="$(printf '%s\n' "$probe" | sed -n 's/^state=//p')"

  case "$state" in
    ready)
      echo "${name}: ready (pid=${pid:-unknown}, port=${port:-n/a}, http=ok)"
      ;;
    partial)
      echo "${name}: partial (pid_running=${pid_running}, port_listening=${port_listening}, http_ready=${http_ready}, pid=${pid:-none})"
      ;;
    *)
      echo "${name}: stopped"
      ;;
  esac
}

http_ok() {
  local url="$1"
  curl -fsS --max-time 2 "$url" >/dev/null 2>&1
}

port_in_use() {
  local port="$1"
  ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "[:.]${port}$"
}

stop_pid_file() {
  local pid_file="$1"
  local label="$2"

  if [[ ! -f "$pid_file" ]]; then
    echo "${label}: not running"
    return 0
  fi

  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    for _ in {1..30}; do
      if ! kill -0 "$pid" 2>/dev/null; then
        rm -f "$pid_file"
        echo "${label}: stopped (pid=${pid})"
        return 0
      fi
      sleep 1
    done
    kill -9 "$pid" 2>/dev/null || true
    rm -f "$pid_file"
    echo "${label}: stopped forcefully (pid=${pid})"
    return 0
  fi

  rm -f "$pid_file"
  echo "${label}: stale pid file removed"
}

start_web_console() {
  if [[ ! -d "$WEB_CONSOLE_DIR" ]]; then
    echo "Web console directory not found: ${WEB_CONSOLE_DIR}" >&2
    return 1
  fi

  if http_ok "${WEB_CONSOLE_URL}"; then
    echo "Web console is already reachable at ${WEB_CONSOLE_URL}."
    return 0
  fi

  if [[ -f "$WEB_PID_FILE" ]]; then
    existing_pid="$(cat "$WEB_PID_FILE" 2>/dev/null || true)"
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
      echo "Web console is already running (pid=${existing_pid})."
      return 0
    fi
    rm -f "$WEB_PID_FILE"
  fi

  if ! command -v npm >/dev/null 2>&1; then
    echo "npm is not installed; cannot start web console." >&2
    return 1
  fi

  if [[ ! -d "${WEB_CONSOLE_DIR}/node_modules" ]]; then
    echo "web-console/node_modules is missing. Run 'cd web-console && npm install' first." >&2
    return 1
  fi

  if port_in_use "${WEB_CONSOLE_PORT}"; then
    echo "Port ${WEB_CONSOLE_PORT} is already in use, and ${WEB_CONSOLE_URL} is not responding." >&2
    echo "Please stop the conflicting process or change VLLM_CLAUDE_WEB_CONSOLE_PORT." >&2
    return 1
  fi

  (
    cd "${WEB_CONSOLE_DIR}"
    nohup npm run dev -- --host 127.0.0.1 --port "${WEB_CONSOLE_PORT}" --strictPort >>"${WEB_CONSOLE_LOG_FILE}" 2>&1 &
    echo $! >"${WEB_PID_FILE}"
  )
  echo "Web console started (pid=$(cat "${WEB_PID_FILE}"))."
  echo "Log file: ${WEB_CONSOLE_LOG_FILE}"
}

wait_for_http() {
  local url="$1"
  local label="$2"

  for _ in {1..30}; do
    if http_ok "$url"; then
      echo "${label} is ready: ${url}"
      return 0
    fi
    sleep 1
  done

  echo "${label} did not become ready: ${url}" >&2
  return 1
}

start_stack() {
  cleanup_on_error() {
    local exit_code="$1"
    if [[ "${START_CLEANUP_NEEDED}" -eq 1 && "${exit_code}" -ne 0 ]]; then
      echo "Startup failed; cleaning up started services..."
      stop_stack
    fi
  }

  trap 'cleanup_on_error $?' RETURN

  echo "Starting llmnode stack..."
  echo "Backend: vLLM"
  echo "Model dir: ${MODEL_DIR}"
  START_CLEANUP_NEEDED=1

  bash "${SCRIPT_DIR}/start_agent.sh" --daemon
  wait_for_http "${AGENT_URL}/health/liveliness" "Agent"

  curl -fsS -X POST "${AGENT_URL}/manage/start" >/dev/null
  echo "vLLM start requested through agent."

  bash "${SCRIPT_DIR}/start_gateway.sh" --daemon
  wait_for_http "${GATEWAY_URL}/health/liveliness" "Gateway"

  start_web_console
  wait_for_http "${WEB_CONSOLE_URL}" "Web console"
  echo "Web console: ${WEB_CONSOLE_URL}"

  START_CLEANUP_NEEDED=0
  trap - RETURN
}

stop_stack() {
  echo "Stopping llmnode stack..."

  if http_ok "${AGENT_URL}/health/liveliness"; then
    curl -fsS -X POST "${AGENT_URL}/manage/stop" >/dev/null || true
    echo "vLLM stop requested through agent."
  else
    bash "${SCRIPT_DIR}/stop_vllm.sh" >/dev/null || true
  fi

  stop_pid_file "$WEB_PID_FILE" "Web console"
  bash "${SCRIPT_DIR}/stop_gateway.sh"
  bash "${SCRIPT_DIR}/stop_agent.sh"
}

restart_stack() {
  stop_stack
  start_stack
}

status_stack() {
  echo "llmnode status"
  echo "project: ${PROJECT_DIR}"
  echo "backend: vLLM"
  echo "model_dir: ${MODEL_DIR}"
  echo "web_console: ${WEB_CONSOLE_URL}"

  print_process_status "gateway" "$GATEWAY_PID_FILE" "4000" "${GATEWAY_URL}/health/liveliness"
  print_process_status "agent" "$AGENT_PID_FILE" "4010" "${AGENT_URL}/state"
  print_process_status "web_console" "$WEB_PID_FILE" "${WEB_CONSOLE_PORT}" "${WEB_CONSOLE_URL}"

  if http_ok "${GATEWAY_URL}/health/liveliness"; then
    echo "gateway_http: ok (${GATEWAY_URL}/health/liveliness)"
  else
    echo "gateway_http: unreachable (${GATEWAY_URL}/health/liveliness)"
  fi

  if http_ok "${AGENT_URL}/state"; then
    echo "agent_http: ok (${AGENT_URL}/state)"
  else
    echo "agent_http: unreachable (${AGENT_URL}/state)"
  fi

  if http_ok "http://127.0.0.1:${VLLM_CLAUDE_VLLM_PORT:-8000}/v1/models"; then
    echo "vllm_http: ok (http://127.0.0.1:${VLLM_CLAUDE_VLLM_PORT:-8000}/v1/models)"
  else
    echo "vllm_http: unreachable (http://127.0.0.1:${VLLM_CLAUDE_VLLM_PORT:-8000}/v1/models)"
  fi

  if http_ok "${WEB_CONSOLE_URL}"; then
    echo "web_console_http: ok (${WEB_CONSOLE_URL})"
  else
    echo "web_console_http: unreachable (${WEB_CONSOLE_URL})"
  fi
}

case "$ACTION" in
  start)
    start_stack
    ;;
  stop)
    stop_stack
    ;;
  restart)
    restart_stack
    ;;
  status)
    status_stack
    ;;
  *)
    echo "Usage: bash scripts/control.sh {start|stop|restart|status}" >&2
    exit 1
    ;;
esac
