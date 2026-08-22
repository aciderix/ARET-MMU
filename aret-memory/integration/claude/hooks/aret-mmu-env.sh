#!/usr/bin/env bash
# Environnement partagé des hooks ARET-MMU.
#
# Objectif : que les hooks démarrent de façon fiable partout, y compris dans un
# conteneur Claude Code **web/cloud tout neuf**, où le venv du projet n'a pas
# encore été créé au moment où SessionStart se déclenche.
#
# Les entrypoints hooks n'utilisent QUE la bibliothèque standard + des modules
# locaux (aucun paquet tiers). Il suffit donc de rendre le paquet importable via
# PYTHONPATH : ni pip ni réseau ni venv ne sont requis pour que les hooks
# tournent. On utilise néanmoins le venv du projet s'il est présent, par cohérence
# avec le serveur MCP.
#
# À sourcer depuis chaque script hook ; expose la fonction `aret_mmu_exec`.

aret_mmu_project_dir="${CLAUDE_PROJECT_DIR:-$(pwd)}"
aret_mmu_dir="${aret_mmu_project_dir}/aret-memory"

# Répertoire mémoire (respecte un override explicite s'il est déjà défini).
export ARET_MEMORY_DIR="${ARET_MEMORY_DIR:-${aret_mmu_dir}/.aret-memory}"

# Rendre le paquet ARET-MMU importable SANS installation (pip/venv non requis).
export PYTHONPATH="${aret_mmu_dir}${PYTHONPATH:+:${PYTHONPATH}}"

# Préférer le venv du projet s'il existe ; sinon, python3 système (suffisant ici).
if [ -x "${aret_mmu_dir}/.venv/bin/python" ]; then
  aret_mmu_python="${aret_mmu_dir}/.venv/bin/python"
else
  aret_mmu_python="python3"
fi

# Exécute un entrypoint hook (nom de fichier relatif à aret-memory/hooks/).
aret_mmu_exec() {
  exec "${aret_mmu_python}" "${aret_mmu_dir}/hooks/$1"
}
