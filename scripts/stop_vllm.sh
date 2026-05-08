#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/runtime_paths.sh"

CONTAINER_NAME="${VLLM_CLAUDE_VLLM_CONTAINER:-qwen36-vllm}"
logger_pid_file="${VLLM_CLAUDE_RUN_DIR}/${CONTAINER_NAME}.logger.pid"

if [[ -f "$logger_pid_file" ]]; then
  logger_pid="$(cat "$logger_pid_file" 2>/dev/null || true)"
  if [[ -n "$logger_pid" ]] && kill -0 "$logger_pid" 2>/dev/null; then
    kill "$logger_pid" 2>/dev/null || true
  fi
  rm -f "$logger_pid_file"
fi

if docker ps -aq -f "name=^${CONTAINER_NAME}$" | grep -q .; then
  docker rm -f "$CONTAINER_NAME"
  echo "Container ${CONTAINER_NAME} stopped and removed."
else
  echo "Container ${CONTAINER_NAME} does not exist."
fi
