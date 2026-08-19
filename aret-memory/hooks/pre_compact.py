"""Hook PreCompact : fournit un paquet de reprise borné avant compression de contexte."""

from __future__ import annotations

from typing import Any

from common import run


def handler(store: Any, payload: dict[str, Any]) -> dict[str, Any]:
    limit = int(payload.get("audit_limit", 12))
    if limit < 1 or limit > 100:
        raise ValueError("audit_limit doit être compris entre 1 et 100")
    front = store.get_front()
    checkpoint = None
    if store.write_enabled:
        checkpoint = store.record_session_checkpoint(
            "PRE_COMPACT", payload.get("session_id"), payload.get("trigger"), None, "aret-hook-precompact"
        )
    return {
        "front": front,
        "recent_audit": store.audit_events(limit),
        "read_after_resume": front["relevant_addresses"],
        "checkpoint": checkpoint,
        "notice": "Checkpoint audit optionnel ; les connaissances durables passent toujours par les outils MCP contrôlés.",
    }


if __name__ == "__main__":
    run("PreCompact", handler)
