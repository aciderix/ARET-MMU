#!/usr/bin/env bash
# PostCompact ARET-MMU : trace optionnellement le résultat ; SessionStart[compact] injecte la reprise.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/aret-mmu-env.sh"
export ARET_HOOK_WRITE_ENABLED="${ARET_HOOK_WRITE_ENABLED:-false}"
aret_mmu_exec post_compact.py
