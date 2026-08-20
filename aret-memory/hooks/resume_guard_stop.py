#!/usr/bin/env python3
"""Feedback Stop de la barrière de reprise ARET-MMU."""
from __future__ import annotations

import json
from pathlib import Path

from common import input_payload
from resume_guard import stop_feedback


def main() -> None:
    payload = input_payload()
    memory_dir = Path(str(payload.get("memory_dir") or __import__("os").environ.get("ARET_MEMORY_DIR") or ".aret-memory"))
    output = stop_feedback(memory_dir, payload)
    if output is not None:
        print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
