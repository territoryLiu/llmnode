#!/usr/bin/env bash
set -euo pipefail

pkill -f "llmnode.agent" || true
