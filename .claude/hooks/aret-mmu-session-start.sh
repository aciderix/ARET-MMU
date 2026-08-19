#!/usr/bin/env bash
# SessionStart ARET-MMU : injecte uniquement le contexte chaud canonique.
set -euo pipefail
export ARET_MEMORY_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}/aret-memory/.aret-memory"
exec python3 "${CLAUDE_PROJECT_DIR:-$(pwd)}/aret-memory/hooks/session_start.py"
