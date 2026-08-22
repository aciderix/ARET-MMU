#!/usr/bin/env bash
# SessionStart ARET-MMU : injecte uniquement le contexte chaud canonique.
set -euo pipefail
export ARET_MEMORY_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}/aret-memory/.aret-memory"
# Pré-chauffe le venv du serveur MCP en arrière-plan (best-effort, non bloquant) :
# une session neuve a ainsi son venv prêt avant le premier appel d'outil mémoire.
# Le lanceur MCP re-bootstrappe le même venv à la demande si ceci est ignoré.
"${CLAUDE_PROJECT_DIR:-$(pwd)}/aret-memory/scripts/bootstrap_venv.sh" >/dev/null 2>&1 &
exec python3 "${CLAUDE_PROJECT_DIR:-$(pwd)}/aret-memory/hooks/session_start.py"
