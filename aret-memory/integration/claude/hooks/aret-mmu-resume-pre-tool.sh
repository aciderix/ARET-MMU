#!/usr/bin/env bash
# PreToolUse ARET-MMU : décision de la barrière de reprise.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/aret-mmu-env.sh"
aret_mmu_exec resume_guard_pre_tool.py
