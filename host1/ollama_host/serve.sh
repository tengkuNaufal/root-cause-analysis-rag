#!/usr/bin/env bash
# Foreground project-local Ollama. Keep NetworkLab open during lab use.
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OLLAMA_PROCESS_HOME="$PROJECT_ROOT/private/runtime/ollama/home"
export OLLAMA_MODELS="$PROJECT_ROOT/private/runtime/ollama/models"
export OLLAMA_HOST=127.0.0.1:11434
export OLLAMA_CONTEXT_LENGTH=2048
export OLLAMA_NUM_PARALLEL=1
export OLLAMA_MAX_LOADED_MODELS=1
export OLLAMA_KEEP_ALIVE=5m
export OLLAMA_NO_CLOUD=1
mkdir -p "$OLLAMA_PROCESS_HOME" "$OLLAMA_MODELS"
exec env HOME="$OLLAMA_PROCESS_HOME" "$PROJECT_ROOT/private/runtime/ollama/dist/bin/ollama" serve
