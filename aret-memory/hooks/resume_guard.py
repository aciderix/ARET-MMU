"""Garde déterministe de reprise ARET-MMU.

Le garde n’accorde l’usage des outils qu’après lecture MCP des adresses critiques.
Son état est purement local et éphémère, sous `.aret-memory/runtime/`, jamais dans SQLite ni Git.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def session_key(payload: dict[str, Any]) -> str:
    raw = str(payload.get("session_id") or payload.get("transcript_path") or payload.get("cwd") or "default")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def runtime_dir(memory_dir: Path) -> Path:
    path = memory_dir / "runtime" / "resume_guard"
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_path(memory_dir: Path, payload: dict[str, Any]) -> Path:
    return runtime_dir(memory_dir) / f"{session_key(payload)}.json"


def load_state(memory_dir: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    path = state_path(memory_dir, payload)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def arm(memory_dir: Path, payload: dict[str, Any], addresses: list[str], reason: str) -> dict[str, Any]:
    canonical = sorted({item for item in addresses if isinstance(item, str) and item.startswith("ARET://knowledge/")})
    armed_at = utc_now()
    state = {
        "version": 1,
        "armed_at": armed_at,
        "reason": reason,
        "status": "active" if canonical else "not_applicable",
        "required_addresses": canonical,
        "remaining_addresses": canonical,
        "completed_at": None if canonical else armed_at,
    }
    path = state_path(memory_dir, payload)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    temporary.replace(path)
    return state


def _addresses_from_input(payload: dict[str, Any]) -> list[str]:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return []
    address = tool_input.get("address")
    addresses = tool_input.get("addresses")
    result: list[str] = []
    if isinstance(address, str):
        result.append(address)
    if isinstance(addresses, list):
        result.extend(item for item in addresses if isinstance(item, str))
    return result


def is_resume_read(payload: dict[str, Any]) -> bool:
    tool_name = str(payload.get("tool_name", ""))
    return (
        tool_name.endswith("__aret_get_resume_protocol")
        or tool_name.endswith("__aret_read")
        or tool_name.endswith("__aret_read_batch")
    )


def _tool_succeeded(payload: dict[str, Any]) -> bool:
    """Refuse de lever le garde sur un échec MCP explicitement signalé."""
    response = payload.get("tool_response")
    if response is None:
        return True
    if isinstance(response, dict):
        if response.get("is_error") is True or response.get("isError") is True:
            return False
        structured = response.get("structured_content") or response.get("structuredContent")
        if isinstance(structured, dict) and structured.get("ok") is False:
            return False
    if isinstance(response, str) and '"ok":false' in response.replace(" ", "").lower():
        return False
    return True


def mark_read(memory_dir: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    state = load_state(memory_dir, payload)
    if state is None or not is_resume_read(payload) or not _tool_succeeded(payload):
        return state
    remaining = set(state.get("remaining_addresses", []))
    for address in _addresses_from_input(payload):
        remaining.discard(address)
    state["remaining_addresses"] = sorted(remaining)
    if not remaining:
        state["completed_at"] = utc_now()
    path = state_path(memory_dir, payload)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    temporary.replace(path)
    return state


def decision(memory_dir: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    state = load_state(memory_dir, payload)
    if state is None or not state.get("remaining_addresses"):
        return None
    if is_resume_read(payload):
        return None
    remaining = state["remaining_addresses"]
    preview = ", ".join(remaining[:6])
    suffix = " …" if len(remaining) > 6 else ""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                "BARRIÈRE DE REPRISE ARET-MMU : lecture canonique obligatoire avant toute autre opération. "
                f"Il reste {len(remaining)} adresse(s) à lire via aret_read/aret_read_batch : {preview}{suffix}"
            ),
            "additionalContext": (
                "La reprise ARET est incomplète. Ne pas poursuivre le travail, ne pas utiliser Bash/Edit/Write et ne pas conclure. "
                "Lire les adresses ARET restantes avec aret_read_batch, puis reprendre seulement lorsque la barrière est levée."
            ),
        }
    }


def stop_feedback(memory_dir: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Force une unique continuation de tour lorsque Claude tente de conclure sans reprise complète."""
    state = load_state(memory_dir, payload)
    if state is None or not state.get("remaining_addresses") or payload.get("stop_hook_active") is True:
        return None
    remaining = state["remaining_addresses"]
    preview = ", ".join(remaining[:6])
    suffix = " …" if len(remaining) > 6 else ""
    return {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": (
                "BARRIÈRE DE REPRISE ARET-MMU ACTIVE : la reprise ne peut pas être considérée terminée. "
                f"Lire les {len(remaining)} pages canoniques restantes avant de répondre ou poursuivre : {preview}{suffix}. "
                "Obtenir les lots via aret_get_resume_protocol, puis appeler aret_read_batch pour chaque lot."
            ),
        }
    }


def memory_dir_from_env() -> Path:
    configured = os.environ.get("ARET_MEMORY_DIR") or ".aret-memory"
    return Path(configured).expanduser().resolve()
