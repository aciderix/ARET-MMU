#!/usr/bin/env bash
# PreCompact ARET-MMU : prépare la reprise et journalise un checkpoint seulement si activé.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/aret-mmu-env.sh"
# La variable est opt-in : aucun checkpoint durable n’est écrit par défaut.
export ARET_HOOK_WRITE_ENABLED="${ARET_HOOK_WRITE_ENABLED:-false}"
aret_mmu_exec pre_compact.py
