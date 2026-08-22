#!/usr/bin/env bash
# Bootstrap idempotent et RAPIDE de l'environnement Python du serveur MCP ARET-MMU.
#
# Pourquoi : dans un conteneur Claude Code éphémère (web/cloud), le venv du projet
# n'existe pas encore au premier démarrage. Un `pip install` complet de `mcp` et de
# ses dépendances compilées prend ~17 s à froid, ce qui DÉPASSE le délai de connexion
# du client MCP : le serveur `aret-memory` n'apparaît alors jamais connecté.
#
# Ce script rend le bootstrap déterministe et court :
#   - chemin CHAUD : si le venv importe déjà `mcp`, il ne fait RIEN (sortie immédiate) ;
#   - chemin FROID : il privilégie `uv` (~1 s) et retombe sur `python -m venv` + `pip`.
#
# Contrats :
#   - toute journalisation va sur stderr (stdout reste réservé au flux MCP stdio) ;
#   - idempotent : rejouable sans effet de bord ;
#   - le paquet ARET-MMU lui-même est importé par PYTHONPATH (pas d'install éditable),
#     donc SEUL `mcp` doit être présent dans le venv.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MMU_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${MMU_DIR}/.venv"
PY="${VENV_DIR}/bin/python"

# Contrainte de version alignée sur aret-memory/pyproject.toml (dépendance `mcp`).
MCP_SPEC="${ARET_MMU_MCP_SPEC:-mcp>=2.0,<3.0}"

log() { printf 'ARET-MMU bootstrap: %s\n' "$*" >&2; }

usable() { [ -x "$PY" ] && "$PY" -c 'import mcp' >/dev/null 2>&1; }

# --- Chemin CHAUD : rien à faire. -------------------------------------------
if usable; then
  exit 0
fi

# --- Chemin FROID : privilégier uv (rapide), sinon repli venv+pip. -----------
if command -v uv >/dev/null 2>&1; then
  log "création du venv via uv…"
  if uv venv "$VENV_DIR" >&2 2>&1; then
    UV_NO_PROGRESS=1 uv pip install --python "$PY" "$MCP_SPEC" >&2 2>&1 || true
  fi
fi

if ! usable; then
  log "repli venv + pip…"
  "${PYTHON_BOOTSTRAP:-python3}" -m venv "$VENV_DIR" >&2 2>&1 || true
  if [ -x "$PY" ]; then
    "$PY" -m pip install --disable-pip-version-check "$MCP_SPEC" >&2 2>&1 || true
  fi
fi

if usable; then
  log "environnement prêt."
  exit 0
fi

log "ÉCHEC : le module 'mcp' reste introuvable après bootstrap (réseau/proxy ?)."
exit 1
