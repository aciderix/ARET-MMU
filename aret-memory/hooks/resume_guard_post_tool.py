#!/usr/bin/env python3
"""Met à jour la barrière de reprise après la confirmation MCP du rituel."""
from __future__ import annotations

import json
from pathlib import Path

from common import input_payload
from resume_guard import acknowledge


def main() -> None:
    payload = input_payload()
    memory_dir = Path(str(payload.get("memory_dir") or __import__("os").environ.get("ARET_MEMORY_DIR") or ".aret-memory"))
    state = acknowledge(memory_dir, payload)
    if state is not None and state.get("acknowledged_at"):
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": (
                    "Rituel de reprise ARET-MMU confirmé : le contexte SQLite injecté a été récapitulé. "
                    "Le travail peut reprendre selon les règles, le Front, les limites de preuve et les pipelines publiés."
                ),
            }
        }, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
