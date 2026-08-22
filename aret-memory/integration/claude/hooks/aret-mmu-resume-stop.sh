#!/usr/bin/env bash
# Stop ARET-MMU : nudge de continuation tant que le rituel n'est pas confirmé.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/aret-mmu-env.sh"
aret_mmu_exec resume_guard_stop.py
