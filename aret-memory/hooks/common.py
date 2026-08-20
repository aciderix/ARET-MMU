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
try:  # Exécution directe des hooks et import comme package de tests.
    from .resume_guard import RITUAL_FIELDS, ritual_prompt
except ImportError:  # pragma: no cover - chemin script Claude Code.
    from resume_guard import RITUAL_FIELDS, ritual_prompt


MCP_TOOL_GROUPS: dict[str, tuple[str, ...]] = {
    "reprise et mémoire": (
        "aret_boot", "aret_restore", "aret_get_front", "aret_get_resume_brief", "aret_get_resume_protocol",
        "aret_acknowledge_resume", "aret_find", "aret_read", "aret_read_batch", "aret_get_forensics", "aret_get_related",
    ),
    "connaissances, preuves et graphe": (
        "aret_get_proofs", "aret_read_artifact", "aret_append_knowledge", "aret_record_proof", "aret_attach_proof",
        "aret_invalidate_proof", "aret_add_relation", "aret_supersede_relation", "aret_register_component",
        "aret_register_function", "aret_register_brick", "aret_update_brick",
    ),
    "Front, roadmap et transport": (
        "aret_update_front", "aret_replace_front", "aret_rebuild_front", "aret_get_roadmap", "aret_export_roadmap",
        "aret_rebuild_index", "aret_export", "aret_export_bundle", "aret_import_bundle", "aret_sync_memory", "aret_export_reference_91",
    ),
    "oracles, industrialisation et assets": (
        "aret_run_oracle", "aret_get_pipeline_catalog", "aret_get_toolchain_status", "aret_run_pipeline",
        "aret_get_pipeline_runs", "aret_read_pipeline_artifact", "aret_get_assets", "aret_register_asset",
    ),
}


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


def _excerpt(item: dict[str, Any]) -> str:
    excerpt = " ".join(str(item.get("content_excerpt", "")).split())
    return excerpt or "Contenu non disponible dans le paquet borné."


def _front_lines(result: dict[str, Any]) -> list[str]:
    front = result.get("front", {})
    state = front.get("state", {}) if isinstance(front, dict) else {}
    lines: list[str] = []
    for key in ("subsystem", "brick", "current_wall", "last_action", "next_action"):
        value = state.get(key, {}) if isinstance(state, dict) else {}
        if isinstance(value, dict) and value.get("value"):
            lines.append(f"{key}: {value['value']}")
    addresses = front.get("relevant_addresses", []) if isinstance(front, dict) else []
    if isinstance(addresses, list) and addresses:
        lines.append("Adresses chaudes : " + ", ".join(str(item) for item in addresses[:12]))
    return lines


def additional_context(result: dict[str, Any]) -> str:
    """Produit le paquet de reprise automatique et son rituel obligatoire.

    Les textes sont extraits de SQLite canonique. Les documents Markdown ayant
    déjà été ingérés, aucun rituel de relecture documentaire n'est demandé.
    """
    lines = [
        "ARET-MMU — reprise automatique depuis SQLite canonique.",
        "Les documents métier sont déjà ingérés : ne les relisez pas par défaut. Approfondissez seulement une adresse précise si le travail le justifie.",
        str(result.get("doctrine", "")),
        "RITUEL OBLIGATOIRE AVANT TOUTE POURSUITE : " + ritual_prompt(),
        "Le contenu de ce récapitulatif doit être produit dans la réponse de reprise avant l’appel MCP de confirmation.",
        "\nÉTAT COURANT / FRONT :",
        *_front_lines(result),
    ]

    git = result.get("git_context", {})
    if isinstance(git, dict):
        if git.get("branch"):
            lines.append("\nGIT — branche : " + str(git["branch"]))
        commits = git.get("recent_commits", [])
        if isinstance(commits, list) and commits:
            lines.append("Derniers commits : " + " | ".join(str(item) for item in commits[:8]))
        working_tree = git.get("working_tree", [])
        if isinstance(working_tree, list) and working_tree:
            lines.append("Arbre Git non propre : " + " | ".join(str(item) for item in working_tree[:12]))

    lines.append("\nLIMITES À RAPPELER DANS LE RÉCAPITULATIF : FIND ne prouve rien ; READ récupère l’objet exact ; PROVEN exige une preuve PASS admissible ; aucun SQL, shell, URL ou push Git arbitraire n’est exposé ; `auto_push=false` reste la politique par défaut ; le document 91 est NOT_APPLICABLE.")

    rules = result.get("rules", [])
    if isinstance(rules, list) and rules:
        lines.append("\nRÈGLES INCONTOURNABLES (injectées depuis SQLite) :")
        for item in rules:
            if isinstance(item, dict):
                lines.append(f"- {item.get('id', '?')} — {item.get('title', '')} : {_excerpt(item)}")

    roadmap = result.get("roadmap", {})
    if isinstance(roadmap, dict):
        bricks = roadmap.get("bricks", [])
        if isinstance(bricks, list) and bricks:
            lines.append("\nROADMAP ACTIVE / BLOQUEURS :")
            for brick in bricks[:8]:
                if isinstance(brick, dict):
                    lines.append(
                        f"- {brick.get('id', '?')} [{brick.get('state', '?')}] M={brick.get('milestone', '?')} "
                        f"priorité={brick.get('priority', '?')} plateforme={brick.get('target_platform', '?')} — {brick.get('title', '')}"
                    )

    catalog = result.get("pipeline_catalog", {})
    if isinstance(catalog, dict):
        lines.append("\nCAPACITÉS D’ANALYSE ET D’INDUSTRIALISATION :")
        lines.append("Les pipelines sont à liste fermée ; `dry_run=true` précède toute génération, réseau ou opération sensible.")
        for policy in ("READ_ONLY", "GENERATE", "NETWORK", "SENSITIVE"):
            names = catalog.get(policy, [])
            if isinstance(names, list) and names:
                lines.append(f"- {policy}: " + ", ".join(str(name) for name in names))
    toolchain = result.get("toolchain_status", {})
    if isinstance(toolchain, dict):
        tools = toolchain.get("tools", {})
        if isinstance(tools, dict):
            available = [name for name, item in tools.items() if isinstance(item, dict) and item.get("available")]
            missing = [name for name, item in tools.items() if isinstance(item, dict) and not item.get("available")]
            lines.append("Toolchain disponible : " + ", ".join(available[:12]))
            if missing:
                lines.append("Toolchain à installer / indisponible : " + ", ".join(missing[:12]))

    lines.append("\nOUTILS MCP DISPONIBLES (par capacité) :")
    for group, tools in MCP_TOOL_GROUPS.items():
        lines.append(f"- {group}: " + ", ".join(tools))

    assets = result.get("assets", [])
    lines.append("\nASSETS / CORPUS DISPONIBLES :")
    if isinstance(assets, list) and assets:
        for asset in assets[:8]:
            if isinstance(asset, dict):
                lines.append(f"- {asset.get('id', '?')} [{asset.get('kind', '?')}] {asset.get('display_name', asset.get('path', '?'))}")
    else:
        lines.append("- Aucun asset canonique enregistré dans le Store à cette reprise.")

    runs = result.get("recent_pipeline_runs", [])
    if isinstance(runs, list) and runs:
        lines.append("\nDERNIERS PIPELINES : " + "; ".join(
            f"{item.get('pipeline_name', '?')}={item.get('result', '?')}" for item in runs[:8] if isinstance(item, dict)
        ))

    journal = result.get("latest_document_71_entries", [])
    if isinstance(journal, list) and journal:
        lines.append("\nDERNIÈRES ÉVOLUTIONS (journal 71, injectées depuis SQLite) :")
        for item in journal:
            if isinstance(item, dict):
                lines.append(f"- {item.get('id', '?')} — {item.get('title', '')} : {_excerpt(item)}")

    audit = result.get("recent_audit", [])
    if isinstance(audit, list) and audit:
        lines.append("\nAUDIT RÉCENT : " + "; ".join(
            f"{item.get('operation', '?')}:{item.get('entity_id', '?')}" for item in audit[:12] if isinstance(item, dict)
        ))

    return "\n".join(line for line in lines if line).strip()[:15000]


def run(hook_name: str, handler: Any) -> None:
    try:
        payload = input_payload()
        result = handler(store_from_payload(payload), payload)
        response: dict[str, Any] = {"ok": True, "hook": hook_name, "result": result}
        if hook_name in {"SessionStart", "PostCompact"}:
            response["hookSpecificOutput"] = {
                "hookEventName": hook_name,
                "additionalContext": additional_context(result),
            }
        emit(response)
    except (AretError, ValueError, json.JSONDecodeError) as exc:
        emit({"ok": False, "hook": hook_name, "error": {"code": type(exc).__name__, "message": str(exc)}})
    except Exception as exc:
        emit({"ok": False, "hook": hook_name, "error": {"code": "INTERNAL_ERROR", "message": str(exc)}})
