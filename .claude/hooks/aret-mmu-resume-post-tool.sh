#!/usr/bin/env bash
set -euo pipefail
export ARET_MEMORY_DIR="${CLAUDE_PROJECT_DIR:?}/aret-memory/.aret-memory"
exec python3 "$CLAUDE_PROJECT_DIR/aret-memory/hooks/resume_guard_post_tool.py"
