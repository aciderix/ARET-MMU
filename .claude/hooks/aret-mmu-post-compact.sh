#!/usr/bin/env bash
# PostCompact ARET-MMU : trace optionnellement le résultat ; SessionStart[compact] injecte la reprise.
set -euo pipefail
export ARET_MEMORY_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}/aret-memory/.aret-memory"
export ARET_HOOK_WRITE_ENABLED="${ARET_HOOK_WRITE_ENABLED:-false}"
exec python3 "${CLAUDE_PROJECT_DIR:-$(pwd)}/aret-memory/hooks/post_compact.py"
