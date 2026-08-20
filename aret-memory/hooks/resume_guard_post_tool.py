#!/usr/bin/env python3
"""Met à jour la barrière de reprise après une lecture MCP ARET."""
from __future__ import annotations

import json
from pathlib import Path

from common import input_payload
from resume_guard import mark_read


def main() -> None:
    payload = input_payload()
    memory_dir = Path(str(payload.get("memory_dir") or __import__("os").environ.get("ARET_MEMORY_DIR") or ".aret-memory"))
    state = mark_read(memory_dir, payload)
    if state is not None and not state.get("remaining_addresses"):
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": "Barrière de reprise ARET-MMU levée : toutes les pages canoniques obligatoires ont été lues. Le travail peut reprendre selon les règles, le Front et les pipelines publiés."
            }
        }, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
