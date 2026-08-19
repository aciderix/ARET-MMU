"""Hook PostCompact : réhydrate le Front canonique après compression de contexte."""

from __future__ import annotations

from typing import Any

from common import run


def handler(store: Any, payload: dict[str, Any]) -> dict[str, Any]:
    boot = store.boot()
    front = store.get_front()
    checkpoint = None
    if store.write_enabled:
        checkpoint = store.record_session_checkpoint(
            "POST_COMPACT", payload.get("session_id"), payload.get("trigger"), payload.get("compact_summary"), "aret-hook-postcompact"
        )
    return {
        "front": front,
        "relevant_addresses": front["relevant_addresses"],
        "doctrine": boot["doctrine"],
        "checkpoint": checkpoint,
        "notice": "SessionStart[compact] réinjecte le Front ; PostCompact trace seulement le résultat de compaction.",
    }


if __name__ == "__main__":
    run("PostCompact", handler)
