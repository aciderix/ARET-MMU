#!/usr/bin/env bash
# PreCompact ARET-MMU : prépare la reprise et journalise un checkpoint seulement si activé.
set -euo pipefail
export ARET_MEMORY_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}/aret-memory/.aret-memory"
# La variable est opt-in : aucun checkpoint durable n’est écrit par défaut.
export ARET_HOOK_WRITE_ENABLED="${ARET_HOOK_WRITE_ENABLED:-false}"
exec python3 "${CLAUDE_PROJECT_DIR:-$(pwd)}/aret-memory/hooks/pre_compact.py"
