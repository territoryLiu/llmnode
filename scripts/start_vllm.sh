#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/runtime_paths.sh"

CONTAINER_NAME="${VLLM_CLAUDE_VLLM_CONTAINER:-qwen36-vllm}"
IMAGE_NAME="${VLLM_CLAUDE_VLLM_IMAGE:-vllm/vllm-openai:nightly}"
MODEL_DIR="${VLLM_CLAUDE_VLLM_MODEL_DIR:-${VLLM_CLAUDE_DIR}/models/Qwen/Qwen3.6-35B-A3B-FP8}"
MODEL_NAME="${VLLM_CLAUDE_VLLM_MODEL_NAME:-qwen36-35b-a3b}"
HOST_PORT="${VLLM_CLAUDE_VLLM_PORT:-8000}"
GPU_MEMORY_UTILIZATION="${VLLM_CLAUDE_VLLM_GPU_MEMORY_UTILIZATION:-0.6}"
TENSOR_PARALLEL_SIZE="${VLLM_CLAUDE_VLLM_TENSOR_PARALLEL_SIZE:-1}"
MAX_MODEL_LEN="${VLLM_CLAUDE_VLLM_MAX_MODEL_LEN:-262144}"
MAX_NUM_SEQS="${VLLM_CLAUDE_VLLM_MAX_NUM_SEQS:-4}"
SHM_SIZE="${VLLM_CLAUDE_VLLM_SHM_SIZE:-16g}"
ENABLE_AUTO_TOOL_CHOICE="${VLLM_CLAUDE_VLLM_ENABLE_AUTO_TOOL_CHOICE:-true}"
REASONING_PARSER="${VLLM_CLAUDE_VLLM_REASONING_PARSER:-qwen3}"
TOOL_CALL_PARSER="${VLLM_CLAUDE_VLLM_TOOL_CALL_PARSER:-qwen3_coder}"

if [[ ! -d "$MODEL_DIR" ]]; then
  echo "Model directory not found: $MODEL_DIR" >&2
  exit 1
fi

if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
  echo "Docker image not found: $IMAGE_NAME" >&2
  exit 1
fi

existing_id="$(docker ps -aq -f "name=^${CONTAINER_NAME}$")"
if [[ -n "$existing_id" ]]; then
  if docker ps -q -f "name=^${CONTAINER_NAME}$" | grep -q .; then
    echo "Container ${CONTAINER_NAME} is already running."
    exit 0
  fi
  docker rm -f "$CONTAINER_NAME" >/dev/null
fi

mkdir -p "${VLLM_CLAUDE_LOG_DIR}" "${VLLM_CLAUDE_RUN_DIR}"
timestamp="$(date '+%Y%m%d-%H%M%S')"
log_file="${VLLM_CLAUDE_LOG_DIR}/${CONTAINER_NAME}-${timestamp}.log"
latest_log_link="${VLLM_CLAUDE_LOG_DIR}/${CONTAINER_NAME}.latest.log"
logger_pid_file="${VLLM_CLAUDE_RUN_DIR}/${CONTAINER_NAME}.logger.pid"

cat > "$log_file" <<EOF
=== llmnode startup ===
timestamp=${timestamp}
container_name=${CONTAINER_NAME}
image_name=${IMAGE_NAME}
model_dir=${MODEL_DIR}
model_name=${MODEL_NAME}
host_port=${HOST_PORT}
gpu_memory_utilization=${GPU_MEMORY_UTILIZATION}
tensor_parallel_size=${TENSOR_PARALLEL_SIZE}
max_model_len=${MAX_MODEL_LEN}
max_num_seqs=${MAX_NUM_SEQS}
shm_size=${SHM_SIZE}
enable_auto_tool_choice=${ENABLE_AUTO_TOOL_CHOICE}
reasoning_parser=${REASONING_PARSER}
tool_call_parser=${TOOL_CALL_PARSER}
==========================

EOF

vllm_args=(
  --model /model
  --served-model-name "$MODEL_NAME"
  --host 0.0.0.0
  --port 8000
  --trust-remote-code
  --tensor-parallel-size "$TENSOR_PARALLEL_SIZE"
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION"
  --max-model-len "$MAX_MODEL_LEN"
  --max-num-seqs "$MAX_NUM_SEQS"
)

if [[ "${ENABLE_AUTO_TOOL_CHOICE,,}" == "true" ]]; then
  vllm_args+=(--reasoning-parser "$REASONING_PARSER" --enable-auto-tool-choice --tool-call-parser "$TOOL_CALL_PARSER")
else
  vllm_args+=(--reasoning-parser "$REASONING_PARSER")
fi

docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  --gpus all \
  --ipc=host \
  --shm-size "$SHM_SIZE" \
  -p "${HOST_PORT}:8000" \
  -v "${MODEL_DIR}:/model:ro" \
  "$IMAGE_NAME" \
  "${vllm_args[@]}"

ln -sfn "$log_file" "$latest_log_link"
nohup stdbuf -oL -eL docker logs -f "$CONTAINER_NAME" >> "$log_file" 2>&1 &
echo $! > "$logger_pid_file"

echo "Container started: ${CONTAINER_NAME}"
echo "Health check: curl http://127.0.0.1:${HOST_PORT}/v1/models"
