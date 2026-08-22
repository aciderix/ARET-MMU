#!/usr/bin/env bash
# Lanceur du serveur MCP ARET-MMU pour les conteneurs Claude Code éphémères.
#
# Objectifs de robustesse (session neuve, redémarrage, post-compaction) :
#   1. Résolution du chemin INDÉPENDANTE de $CLAUDE_PROJECT_DIR : tout est déduit
#      de l'emplacement réel de ce script, donc un $CLAUDE_PROJECT_DIR vide ne
#      casse rien une fois le script lancé.
#   2. Démarrage RAPIDE : le venv est amené via bootstrap_venv.sh (uv-first, ~1 s
#      à froid, immédiat à chaud), bien en deçà du délai de connexion MCP.
#   3. Repli : si le venv est indisponible, on tente python3 système (les hooks
#      peuvent avoir déjà rendu `mcp` importable) ; le paquet ARET-MMU est fourni
#      par PYTHONPATH, sans install éditable.
#   4. stdout reste EXCLUSIVEMENT le flux MCP stdio ; toute journalisation → stderr.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MMU_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "${MMU_DIR}/.." && pwd)}"
VENV_DIR="${MMU_DIR}/.venv"

# Amène l'environnement Python (idempotent, rapide, journalise sur stderr).
# Non fatal : en cas d'échec on tente quand même le python système ci-dessous.
"${SCRIPT_DIR}/bootstrap_venv.sh" || true

# Interpréteur : venv du projet en priorité, sinon python3 système.
if [ -x "${VENV_DIR}/bin/python" ]; then
  ARET_PYTHON="${VENV_DIR}/bin/python"
else
  ARET_PYTHON="python3"
fi

# Le paquet ARET-MMU est importé sans installation (cohérent avec les hooks).
export PYTHONPATH="${MMU_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

# La configuration MCP peut passer ARET_WRITE_ENABLED=true pour une session d'écriture ;
# en l'absence de décision explicite, le serveur reste en lecture seule.
export ARET_WRITE_ENABLED="${ARET_WRITE_ENABLED:-false}"
export CLAUDE_PROJECT_DIR="${PROJECT_DIR}"

exec "${ARET_PYTHON}" "${MMU_DIR}/aret_mmu_server.py" "$@"
