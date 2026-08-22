#!/usr/bin/env bash
# PostToolUse ARET-MMU : lève la garde après un acquittement de reprise réussi.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/aret-mmu-env.sh"
aret_mmu_exec resume_guard_post_tool.py
