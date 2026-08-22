#!/usr/bin/env bash
# SessionStart ARET-MMU : injecte uniquement le contexte chaud canonique.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/aret-mmu-env.sh"
aret_mmu_exec session_start.py
