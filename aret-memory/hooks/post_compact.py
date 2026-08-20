"""Hook PostCompact : réhydrate le Front canonique après compression de contexte."""

from __future__ import annotations

from typing import Any

from common import repository_context, run
from resume_guard import arm


def handler(store: Any, payload: dict[str, Any]) -> dict[str, Any]:
    boot = store.boot()
    front = store.get_front()
    protocol = store.get_resume_protocol()
    guard = arm(store.memory_dir, payload, protocol["required_addresses"], reason="PostCompact")
    protocol_summary = {
        "protocol_version": protocol["protocol_version"], "required_address_count": protocol["required_address_count"],
        "batch_count": protocol["batch_count"], "instructions": protocol["instructions"],
    }
    checkpoint = None
    if store.write_enabled:
        checkpoint = store.record_session_checkpoint(
            "POST_COMPACT", payload.get("session_id"), payload.get("trigger"), payload.get("compact_summary"), "aret-hook-postcompact"
        )
    return {
        "front": front,
        "relevant_addresses": front["relevant_addresses"],
        "doctrine": boot["doctrine"],
        "git_context": repository_context(),
        "checkpoint": checkpoint,
        "resume_protocol": protocol_summary,
        "resume_guard": {
            "armed_at": guard["armed_at"], "reason": guard["reason"],
            "remaining_address_count": len(guard["remaining_addresses"]),
        },
        "notice": "PostCompact arme la barrière de reprise. PreToolUse refuse toute opération hors lecture MCP tant que les lots du protocole ne sont pas lus ; Stop relance l’agent une fois s’il tente de conclure trop tôt.",
    }


if __name__ == "__main__":
    run("PostCompact", handler)
