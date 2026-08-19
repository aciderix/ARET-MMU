"""Primitives de transport pour les hooks ARET-MMU, sans sortie parasite sur stdout."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.repository import AretError, MemoryStore


def input_payload() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    decoded = json.loads(raw)
    if not isinstance(decoded, dict):
        raise ValueError("Le payload de hook doit être un objet JSON")
    return decoded


def store_from_payload(payload: dict[str, Any]) -> MemoryStore:
    configured = payload.get("memory_dir") or os.environ.get("ARET_MEMORY_DIR") or ".aret-memory"
    checkpoint_writes = os.environ.get("ARET_HOOK_WRITE_ENABLED", "false").lower() == "true"
    return MemoryStore(Path(str(configured)), write_enabled=checkpoint_writes)


def emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def additional_context(result: dict[str, Any]) -> str:
    """Produit le contexte chaud minimal injecté exclusivement au SessionStart."""
    front = result.get("front", {})
    state = front.get("state", {}) if isinstance(front, dict) else {}
    addresses = front.get("relevant_addresses", []) if isinstance(front, dict) else []
    lines = [
        "ARET-MMU — contexte restauré depuis SQLite canonique.",
        str(result.get("doctrine", "")),
        "Utiliser FIND pour découvrir, puis READ/READ_BATCH sur des adresses explicites.",
    ]
    for key in ("subsystem", "brick", "current_wall", "last_action", "next_action"):
        value = state.get(key, {}) if isinstance(state, dict) else {}
        if isinstance(value, dict) and value.get("value"):
            lines.append(f"{key}: {value['value']}")
    if addresses:
        lines.append("Adresses pertinentes : " + ", ".join(str(item) for item in addresses[:12]))
    return "\n".join(line for line in lines if line).strip()[:9500]


def run(hook_name: str, handler: Any) -> None:
    try:
        payload = input_payload()
        result = handler(store_from_payload(payload), payload)
        response: dict[str, Any] = {"ok": True, "hook": hook_name, "result": result}
        if hook_name == "SessionStart":
            response["hookSpecificOutput"] = {
                "hookEventName": "SessionStart",
                "additionalContext": additional_context(result),
            }
        emit(response)
    except (AretError, ValueError, json.JSONDecodeError) as exc:
        emit({"ok": False, "hook": hook_name, "error": {"code": type(exc).__name__, "message": str(exc)}})
    except Exception as exc:
        emit({"ok": False, "hook": hook_name, "error": {"code": "INTERNAL_ERROR", "message": str(exc)}})
