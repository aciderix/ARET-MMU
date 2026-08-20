#!/usr/bin/env python3
"""Arme la barrière de reprise après SessionStart ou PostCompact."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from common import input_payload
from core.repository import MemoryStore
from resume_guard import arm


def main() -> None:
    payload = input_payload()
    memory_dir = Path(str(payload.get("memory_dir") or __import__("os").environ.get("ARET_MEMORY_DIR") or ".aret-memory"))
    store = MemoryStore(memory_dir, write_enabled=False)
    protocol = store.get_resume_protocol()
    state = arm(memory_dir, payload, protocol["required_addresses"], reason=str(payload.get("hook_event_name", "resume")))
    output = {
        "protocol": protocol,
        "state": state,
        "additional_context": (
            "RITUEL DE REPRISE ARET-MMU OBLIGATOIRE. Avant toute analyse, édition, commande, génération ou conclusion, "
            f"lire {protocol['required_address_count']} pages canoniques en {protocol['batch_count']} lots via aret_get_resume_protocol puis aret_read_batch. "
            "La barrière PreToolUse bloque toute autre opération jusqu’à la lecture complète."
        ),
    }
    print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
