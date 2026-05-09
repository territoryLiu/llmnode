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
WEB_CONSOLE_ROOT_MARKER="${WEB_CONSOLE_DIR}/src/main.tsx"
LAST_WEB_CONSOLE_ADOPTION_PID=""

print_header() {
  local title="$1"
  printf '\n== %s ==\n' "${title}"
}

print_kv() {
  local key="$1"
  local value="$2"
  printf '  %-14s %s\n' "${key}" "${value}"
}

print_step() {
  local label="$1"
  printf '[step] %s\n' "${label}"
}

print_info() {
  local label="$1"
  local value="$2"
  printf '[info] %s: %s\n' "${label}" "${value}"
}

print_success() {
  local message="$1"
  printf '[ok] %s\n' "${message}"
}

print_warn() {
  local message="$1"
  printf '[warn] %s\n' "${message}"
}

print_error() {
  local message="$1"
  printf '[error] %s\n' "${message}" >&2
}

print_summary_state() {
  local state="$1"
  local detail="$2"
  print_header "summary"
  print_kv "stack_state" "${state}"
  print_kv "detail" "${detail}"
}

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
      printf '  %-12s ready   pid=%s  port=%s  http=ok\n' "${name}" "${pid:-unknown}" "${port:-n/a}"
      ;;
    partial)
      printf '  %-12s partial pid=%s  port=%s  pid_running=%s  port_listening=%s  http_ready=%s\n' \
        "${name}" "${pid:-none}" "${port:-n/a}" "${pid_running}" "${port_listening}" "${http_ready}"
      ;;
    *)
      printf '  %-12s stopped\n' "${name}"
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

find_web_console_pid() {
  pgrep -f "node .*${WEB_CONSOLE_DIR}/node_modules/.bin/vite( .*)?--port ${WEB_CONSOLE_PORT}" | head -n 1 || true
}

web_console_matches_project() {
  local homepage
  homepage="$(curl -fsS --max-time 2 "${WEB_CONSOLE_URL}" 2>/dev/null || true)"
  [[ -n "${homepage}" ]] && grep -Fq '/src/main.tsx' <<<"${homepage}"
}

adopt_web_console_pid_if_needed() {
  LAST_WEB_CONSOLE_ADOPTION_PID=""

  if [[ -f "${WEB_PID_FILE}" ]]; then
    local existing_pid
    existing_pid="$(cat "${WEB_PID_FILE}" 2>/dev/null || true)"
    if [[ -n "${existing_pid}" ]] && kill -0 "${existing_pid}" 2>/dev/null; then
      return 0
    fi
    rm -f "${WEB_PID_FILE}"
  fi

  local detected_pid
  detected_pid="$(find_web_console_pid)"
  if [[ -n "${detected_pid}" ]]; then
    echo "${detected_pid}" >"${WEB_PID_FILE}"
    LAST_WEB_CONSOLE_ADOPTION_PID="${detected_pid}"
    return 0
  fi

  return 1
}

stop_pid_file() {
  local pid_file="$1"
  local label="$2"

  if [[ ! -f "$pid_file" ]]; then
    print_info "${label}" "not running"
    return 0
  fi

  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    for _ in {1..30}; do
      if ! kill -0 "$pid" 2>/dev/null; then
        rm -f "$pid_file"
        print_success "${label} stopped (pid=${pid})"
        return 0
      fi
      sleep 1
    done
    kill -9 "$pid" 2>/dev/null || true
    rm -f "$pid_file"
    print_warn "${label} stopped forcefully (pid=${pid})"
    return 0
  fi

  rm -f "$pid_file"
  print_warn "${label} stale pid file removed"
}

start_web_console() {
  if [[ ! -d "$WEB_CONSOLE_DIR" ]]; then
    print_error "Web console directory not found: ${WEB_CONSOLE_DIR}"
    return 1
  fi

  if web_console_matches_project; then
    adopt_web_console_pid_if_needed || true
    if [[ -n "${LAST_WEB_CONSOLE_ADOPTION_PID}" ]]; then
      print_info "web-console" "adopted existing Vite process (pid=${LAST_WEB_CONSOLE_ADOPTION_PID})"
    fi
    print_success "Web console already reachable at ${WEB_CONSOLE_URL}"
    return 0
  fi

  if [[ -f "$WEB_PID_FILE" ]]; then
    existing_pid="$(cat "$WEB_PID_FILE" 2>/dev/null || true)"
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
      print_info "web-console" "already running (pid=${existing_pid})"
      return 0
    fi
    rm -f "$WEB_PID_FILE"
  fi

  if ! command -v npm >/dev/null 2>&1; then
    print_error "npm is not installed; cannot start web console"
    return 1
  fi

  if [[ ! -d "${WEB_CONSOLE_DIR}/node_modules" ]]; then
    print_error "web-console/node_modules is missing. Run 'cd web-console && npm install' first"
    return 1
  fi

  if port_in_use "${WEB_CONSOLE_PORT}"; then
    print_error "Port ${WEB_CONSOLE_PORT} is already in use, and ${WEB_CONSOLE_URL} is not responding"
    print_error "Please stop the conflicting process or change VLLM_CLAUDE_WEB_CONSOLE_PORT"
    return 1
  fi

  (
    cd "${WEB_CONSOLE_DIR}"
    nohup npm run dev -- --host 127.0.0.1 --port "${WEB_CONSOLE_PORT}" --strictPort >>"${WEB_CONSOLE_LOG_FILE}" 2>&1 &
    echo $! >"${WEB_PID_FILE}"
  )
  print_success "Web console started (pid=$(cat "${WEB_PID_FILE}"))"
  print_info "log" "${WEB_CONSOLE_LOG_FILE}"
}

wait_for_http() {
  local url="$1"
  local label="$2"

  for _ in {1..30}; do
    if http_ok "$url"; then
      print_success "${label} ready at ${url}"
      return 0
    fi
    sleep 1
  done

  print_error "${label} did not become ready: ${url}"
  return 1
}

start_stack() {
  cleanup_on_error() {
    local exit_code="$1"
    if [[ "${START_CLEANUP_NEEDED}" -eq 1 && "${exit_code}" -ne 0 ]]; then
      print_error "Startup failed; cleaning up started services"
      stop_stack
    fi
  }

  trap 'cleanup_on_error $?' RETURN

  print_header "llmnode start"
  print_kv "backend" "vLLM"
  print_kv "model_dir" "${MODEL_DIR}"
  print_kv "gateway" "${GATEWAY_URL}"
  print_kv "agent" "${AGENT_URL}"
  print_kv "web_console" "${WEB_CONSOLE_URL}"
  START_CLEANUP_NEEDED=1

  print_step "starting node-agent"
  bash "${SCRIPT_DIR}/start_agent.sh" --daemon >/dev/null
  print_success "Node agent started (pid=$(cat "${AGENT_PID_FILE}" 2>/dev/null || echo unknown))"
  print_info "log" "${VLLM_CLAUDE_LOG_DIR}/agent.log"
  wait_for_http "${AGENT_URL}/health/liveliness" "Agent"

  print_step "requesting vLLM start through agent"
  curl -fsS -X POST "${AGENT_URL}/manage/start" >/dev/null
  print_success "vLLM start requested through agent"

  print_step "starting gateway-api"
  bash "${SCRIPT_DIR}/start_gateway.sh" --daemon >/dev/null
  print_success "Gateway started (pid=$(cat "${GATEWAY_PID_FILE}" 2>/dev/null || echo unknown))"
  print_info "log" "${VLLM_CLAUDE_LOG_DIR}/gateway.log"
  wait_for_http "${GATEWAY_URL}/health/liveliness" "Gateway"

  print_step "starting web-console"
  start_web_console
  wait_for_http "${WEB_CONSOLE_URL}" "Web console"

  print_header "stack ready"
  print_kv "gateway" "${GATEWAY_URL}"
  print_kv "agent" "${AGENT_URL}"
  print_kv "web_console" "${WEB_CONSOLE_URL}"
  print_kv "next" "Run 'bash scripts/control.sh status' for a full health summary"

  START_CLEANUP_NEEDED=0
  trap - RETURN
}

stop_stack() {
  print_header "llmnode stop"

  if http_ok "${AGENT_URL}/health/liveliness"; then
    print_step "requesting vLLM stop through agent"
    curl -fsS -X POST "${AGENT_URL}/manage/stop" >/dev/null || true
    print_success "vLLM stop requested through agent"
  else
    print_step "stopping vLLM directly"
    bash "${SCRIPT_DIR}/stop_vllm.sh" >/dev/null || true
  fi

  print_step "stopping web-console"
  adopt_web_console_pid_if_needed || true
  stop_pid_file "$WEB_PID_FILE" "Web console"
  print_step "stopping gateway-api"
  bash "${SCRIPT_DIR}/stop_gateway.sh" >/dev/null || true
  print_success "Gateway stop sequence completed"
  print_step "stopping node-agent"
  bash "${SCRIPT_DIR}/stop_agent.sh" >/dev/null || true
  print_success "Node agent stop sequence completed"

  print_header "stack stopped"
  print_kv "result" "agent, gateway, vLLM, and web-console stop sequence completed"
}

restart_stack() {
  print_header "llmnode restart"
  print_info "action" "stop current stack, then start again"
  stop_stack
  start_stack
}

status_stack() {
  print_header "llmnode status"
  print_kv "project" "${PROJECT_DIR}"
  print_kv "backend" "vLLM"
  print_kv "model_dir" "${MODEL_DIR}"
  print_kv "web_console" "${WEB_CONSOLE_URL}"

  if web_console_matches_project; then
    adopt_web_console_pid_if_needed || true
    if [[ -n "${LAST_WEB_CONSOLE_ADOPTION_PID}" ]]; then
      print_info "web-console" "adopted existing Vite process (pid=${LAST_WEB_CONSOLE_ADOPTION_PID})"
    fi
  fi

  print_header "processes"
  print_process_status "gateway" "$GATEWAY_PID_FILE" "4000" "${GATEWAY_URL}/health/liveliness"
  print_process_status "agent" "$AGENT_PID_FILE" "4010" "${AGENT_URL}/state"
  print_process_status "web_console" "$WEB_PID_FILE" "${WEB_CONSOLE_PORT}" "${WEB_CONSOLE_URL}"

  local gateway_http_state="unreachable"
  if http_ok "${GATEWAY_URL}/health/liveliness"; then
    gateway_http_state="ok"
  fi

  local agent_http_state="unreachable"
  if http_ok "${AGENT_URL}/state"; then
    agent_http_state="ok"
  fi

  local vllm_http_state="unreachable"
  if http_ok "http://127.0.0.1:${VLLM_CLAUDE_VLLM_PORT:-8000}/v1/models"; then
    vllm_http_state="ok"
  fi

  local web_console_http_state="unreachable"
  if http_ok "${WEB_CONSOLE_URL}"; then
    web_console_http_state="ok"
  fi

  local stack_state="partial"
  local stack_detail="Some services are available, but the stack is not fully ready yet."

  if [[ "${gateway_http_state}" == "unreachable" && "${agent_http_state}" == "unreachable" && "${vllm_http_state}" == "unreachable" && "${web_console_http_state}" == "unreachable" ]]; then
    stack_state="stopped"
    stack_detail="No managed services are currently reachable."
  elif [[ "${gateway_http_state}" == "ok" && "${agent_http_state}" == "ok" && "${vllm_http_state}" == "ok" && "${web_console_http_state}" == "ok" ]]; then
    stack_state="ready"
    stack_detail="Gateway, agent, vLLM, and web-console are all reachable."
  elif [[ "${gateway_http_state}" == "ok" && "${agent_http_state}" == "ok" && "${web_console_http_state}" == "ok" && "${vllm_http_state}" == "unreachable" ]]; then
    stack_state="warming"
    stack_detail="Control plane is up, and vLLM is still warming up or loading the model."
  fi

  print_summary_state "${stack_state}" "${stack_detail}"

  print_header "http health"
  print_kv "gateway_http" "${gateway_http_state} (${GATEWAY_URL}/health/liveliness)"
  print_kv "agent_http" "${agent_http_state} (${AGENT_URL}/state)"
  print_kv "vllm_http" "${vllm_http_state} (http://127.0.0.1:${VLLM_CLAUDE_VLLM_PORT:-8000}/v1/models)"
  print_kv "web_console_http" "${web_console_http_state} (${WEB_CONSOLE_URL})"
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
