#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "${DIR}/.env" ]]; then
  # shellcheck disable=SC1090
  source "${DIR}/.env"
fi
export PYTHONPATH="${DIR}/src:${PYTHONPATH:-}"
if [[ -x "/home/heshan/.conda/envs/paper2any/bin/python" ]]; then
  exec /home/heshan/.conda/envs/paper2any/bin/python -m llmnode.agent
fi
exec python -m llmnode.agent
