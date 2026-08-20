#!/usr/bin/env bash
# Bootstrap idempotent ARET-MMU pour les conteneurs Claude Code éphémères.
# Toute journalisation est redirigée vers stderr : stdout reste exclusivement MCP stdio.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MMU_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "${MMU_DIR}/.." && pwd)}"
VENV_DIR="${MMU_DIR}/.venv"
BOOTSTRAP_PYTHON="${PYTHON_BOOTSTRAP:-python3}"
STAMP_FILE="${VENV_DIR}/.aret-mmu-pyproject.sha256"
PYPROJECT_FILE="${MMU_DIR}/pyproject.toml"

if ! command -v "${BOOTSTRAP_PYTHON}" >/dev/null 2>&1; then
  printf 'ARET-MMU bootstrap: interpréteur Python introuvable: %s\n' "${BOOTSTRAP_PYTHON}" >&2
  exit 127
fi

if [ ! -f "${PYPROJECT_FILE}" ]; then
  printf 'ARET-MMU bootstrap: pyproject.toml introuvable: %s\n' "${PYPROJECT_FILE}" >&2
  exit 1
fi

if [ ! -x "${VENV_DIR}/bin/python" ]; then
  printf 'ARET-MMU bootstrap: création du venv Python…\n' >&2
  "${BOOTSTRAP_PYTHON}" -m venv "${VENV_DIR}" >&2
fi

CURRENT_PYPROJECT_SHA="$(sha256sum "${PYPROJECT_FILE}" | awk '{print $1}')"
INSTALLED_PYPROJECT_SHA=""
if [ -f "${STAMP_FILE}" ]; then
  INSTALLED_PYPROJECT_SHA="$(cat "${STAMP_FILE}")"
fi

if [ "${CURRENT_PYPROJECT_SHA}" != "${INSTALLED_PYPROJECT_SHA}" ]; then
  printf 'ARET-MMU bootstrap: installation ou mise à jour des dépendances Python…\n' >&2
  "${VENV_DIR}/bin/python" -m pip install --disable-pip-version-check -e "${MMU_DIR}" >&2
  printf '%s\n' "${CURRENT_PYPROJECT_SHA}" > "${STAMP_FILE}"
fi

# La configuration MCP peut explicitement passer true pour une session d’écriture.
# En l’absence de décision explicite, le serveur reste lecture seule.
export ARET_WRITE_ENABLED="${ARET_WRITE_ENABLED:-false}"
export CLAUDE_PROJECT_DIR="${PROJECT_DIR}"

exec "${VENV_DIR}/bin/python" "${MMU_DIR}/aret_mmu_server.py" "$@"
