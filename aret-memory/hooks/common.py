"""Primitives de transport pour les hooks ARET-MMU, sans sortie parasite sur stdout."""

from __future__ import annotations

import json
import os
import subprocess
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


def repository_context() -> dict[str, Any]:
    """Retourne un état Git borné et strictement en lecture pour les reprises Claude."""
    repository = PROJECT_ROOT.parent
    try:
        branch = subprocess.run(["git", "-C", str(repository), "branch", "--show-current"], capture_output=True, text=True, timeout=3, check=False).stdout.strip()
        status = subprocess.run(["git", "-C", str(repository), "status", "--short"], capture_output=True, text=True, timeout=3, check=False).stdout.splitlines()
        commits = subprocess.run(["git", "-C", str(repository), "log", "-8", "--pretty=format:%h %s"], capture_output=True, text=True, timeout=3, check=False).stdout.splitlines()
        return {"branch": branch, "working_tree": status[:20], "recent_commits": commits[:8]}
    except (OSError, subprocess.TimeoutExpired):
        return {"branch": "unknown", "working_tree": [], "recent_commits": [], "unavailable": True}


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
    catalog = result.get("pipeline_catalog", {})
    if isinstance(catalog, dict):
        lines.append("Pipelines ARET : consulter aret_get_pipeline_catalog ; dry_run obligatoire avant génération, réseau ou opération sensible.")
        for policy in ("READ_ONLY", "GENERATE", "NETWORK", "SENSITIVE"):
            names = catalog.get(policy, [])
            if isinstance(names, list) and names:
                shown = ", ".join(str(name) for name in names[:10])
                suffix = " …" if len(names) > 10 else ""
                lines.append(f"{policy}: {shown}{suffix}")
    recent_runs = result.get("recent_pipeline_runs", [])
    if isinstance(recent_runs, list) and recent_runs:
        summary = "; ".join(
            f"{item.get('pipeline_name', '?')}={item.get('result', '?')}" for item in recent_runs[:8] if isinstance(item, dict)
        )
        if summary:
            lines.append("Derniers pipelines : " + summary)
    rules = result.get("rules", [])
    if isinstance(rules, list) and rules:
        lines.append("Règles incontournables à lire : " + "; ".join(
            f"{item.get('id', '?')} — {item.get('title', '')}" for item in rules[:12] if isinstance(item, dict)
        ))
    journal = result.get("latest_document_71_entries", [])
    if isinstance(journal, list) and journal:
        lines.append("Dernières entrées 71 à lire : " + "; ".join(
            f"{item.get('id', '?')} — {item.get('title', '')}" for item in journal[:8] if isinstance(item, dict)
        ))
    audit = result.get("recent_audit", [])
    if isinstance(audit, list) and audit:
        lines.append("Audit récent : " + "; ".join(
            f"{item.get('operation', '?')}:{item.get('entity_id', '?')}" for item in audit[:8] if isinstance(item, dict)
        ))
    git = result.get("git_context", {})
    if isinstance(git, dict):
        if git.get("branch"):
            lines.append("Git branche : " + str(git["branch"]))
        commits = git.get("recent_commits", [])
        if isinstance(commits, list) and commits:
            lines.append("Derniers commits : " + " | ".join(str(item) for item in commits[:8]))
        working_tree = git.get("working_tree", [])
        if isinstance(working_tree, list) and working_tree:
            lines.append("Arbre Git non propre : " + " | ".join(str(item) for item in working_tree[:12]))
    protocol = result.get("resume_protocol", {})
    guard = result.get("resume_guard", {})
    if isinstance(protocol, dict):
        count = protocol.get("required_address_count")
        batches = protocol.get("batch_count")
        if count and batches:
            lines.append(
                f"BARRIÈRE DE REPRISE OBLIGATOIRE : {count} pages canoniques à lire en {batches} lots via aret_get_resume_protocol puis aret_read_batch. "
                "PreToolUse refuse toute autre opération ; ne pas reprendre, éditer, tester, générer ou conclure avant levée."
            )
    if isinstance(guard, dict) and guard.get("remaining_addresses"):
        lines.append(f"Barrière armée : {len(guard['remaining_addresses'])} lecture(s) restante(s).")
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
