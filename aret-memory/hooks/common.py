"""Primitives de transport pour les hooks ARET-MMU, sans sortie parasite sur stdout."""

from __future__ import annotations

import hashlib
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


HOOK_CONTEXT_MAX_BYTES = 18_500

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
        "aret_update_front", "aret_replace_front", "aret_prepare_handoff", "aret_rebuild_front", "aret_get_roadmap",
        "aret_export_roadmap", "aret_rebuild_index", "aret_export", "aret_export_bundle", "aret_import_bundle",
        "aret_sync_memory", "aret_export_reference_91",
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


def _front_lines(front: dict[str, Any]) -> list[str]:
    state = front.get("state", {}) if isinstance(front, dict) else {}
    lines: list[str] = []
    for key in ("subsystem", "brick", "current_wall", "last_action", "next_action"):
        value = state.get(key, {}) if isinstance(state, dict) else {}
        if isinstance(value, dict) and value.get("value"):
            lines.append(f"{key}: {value['value']}")
    return lines


def _compact_tool_groups() -> str:
    return " ; ".join(f"{group}: {', '.join(tools)}" for group, tools in MCP_TOOL_GROUPS.items())


def _technical_checkpoint_lines(handoff: dict[str, Any]) -> list[str]:
    checkpoint = handoff.get("technical_checkpoint", {}) if isinstance(handoff, dict) else {}
    if not isinstance(checkpoint, dict) or checkpoint.get("state") == "NONE":
        return [
            "\\n### CHECKPOINT TECHNIQUE — GESTE INTERROMPU",
            "Aucun checkpoint technique actif : aucun geste technique ne doit être inventé pour cette reprise.",
        ]
    verification = checkpoint.get("last_validation_machine_status", {})
    status = verification.get("status", "DECLARED_UNVERIFIED") if isinstance(verification, dict) else "DECLARED_UNVERIFIED"
    if status == "MACHINE_VERIFIED":
        validation_note = "MACHINE_VERIFIED : " + str(verification.get("address", "")) + " → " + str(verification.get("result", ""))
    elif status == "DECLARED_UNVERIFIED":
        validation_note = "DÉCLARÉ — NON VÉRIFIÉ PAR MCP : aucune adresse pipeline/preuve canonique n’accompagne ce verdict."
    else:
        validation_note = "Aucun verdict machine déclaré dans ce checkpoint."
    return [
        "\\n### CHECKPOINT TECHNIQUE — GESTE INTERROMPU",
        "Cible exacte : " + str(checkpoint.get("handoff_technical_target", "")),
        "Dernier changement : " + str(checkpoint.get("handoff_technical_change", "")),
        "État d’exécution : " + str(checkpoint.get("handoff_execution_state", "")),
        "Dernière validation déclarée : " + str(checkpoint.get("handoff_last_validation", "")),
        "Statut de cette déclaration : " + validation_note,
        "Actions immédiates : " + str(checkpoint.get("handoff_immediate_actions", "")),
    ]


def _observation_lines(dossier: dict[str, Any]) -> list[str]:
    observations = dossier.get("observations", {}) if isinstance(dossier, dict) else {}
    if not isinstance(observations, dict):
        observations = {}
    total = int(observations.get("total", 0) or 0)
    items = observations.get("items", [])
    lines = ["\\n### OBSERVATIONS MCP FACTUELLES DEPUIS LE CHECKPOINT"]
    if not isinstance(items, list) or not items:
        lines.append("Aucune observation MCP résultat-portante depuis le checkpoint. Cela ne permet pas de conclure qu’aucune action hors MCP n’a eu lieu.")
        return lines
    lines.append(f"{len(items)} dernière(s) observation(s) affichée(s) sur {total} fait(s) machine disponible(s).")
    for item in items:
        if not isinstance(item, dict):
            continue
        parameters = str(item.get("parameters", "")).strip()
        suffix = f" ; paramètres: {parameters}" if parameters else ""
        lines.append(
            f"- [{item.get('timestamp', '?')}] {item.get('kind', '?')} {item.get('name', '?')} → {item.get('result', '?')}"
            f" | {item.get('address', '?')} | artefact sha256: {item.get('artifact_hash', '')}{suffix}"
        )
    lines.append("Ces faits observés ne décrivent ni intention, ni correctif, ni prochaine action.")
    return lines


def _catastrophic_dossier(exc: Exception) -> dict[str, Any]:
    """Dossier minimal non-prêt quand SQLite lui-même est illisible : jamais silencieux."""
    reason = f"Dossier de reprise illisible : {exc}"
    return {
        "ready": False,
        "errors": [reason],
        "playbook": {"entries": []},
        "handoff": {},
        "front": {},
        "observations": {"total": 0, "items": []},
        "contract_hash": hashlib.sha256(("DEGRADED:" + reason).encode("utf-8")).hexdigest(),
    }


def resume_context_or_degraded(store: MemoryStore) -> tuple[dict[str, Any], bool]:
    """Retourne (contexte, degraded). Ne lève JAMAIS : une mémoire incomplète ou
    illisible produit un contexte DÉGRADÉ (avec un contract_hash valide pour armer la
    barrière), au lieu de faire échouer le hook en silence — l'armement fail-open était
    le seul cas où une reprise cassée laissait l'agent poursuivre sans garde."""
    try:
        return store.get_resume_context(journal_limit=8, rule_limit=12, excerpt_bytes=260), False
    except AretError as exc:
        try:
            dossier = store.get_resume_dossier()
        except Exception as inner:  # SQLite illisible, playbook corrompu, etc.
            dossier = _catastrophic_dossier(inner)
        try:
            front = store.get_front()
        except Exception:
            front = {"state": {}, "relevant_addresses": []}
        context = {
            "resume_dossier": dossier,
            "front": front,
            "degraded_reason": str(exc),
            "doctrine": "", "roadmap": {}, "assets": [], "recent_audit": [],
            "memory_format_version": "", "policy_version": "",
            "notice": "MÉMOIRE DE REPRISE DÉGRADÉE : le dossier n'est pas complet ; ne poursuivez pas comme si la reprise était normale.",
        }
        return context, True


def _degraded_additional_context(dossier: dict[str, Any]) -> str:
    """Contexte injecté quand le dossier n'est PAS prêt : bruyant, les lois restent
    autoritatives, la barrière est active. Jamais une reprise silencieusement absente."""
    entries = dossier.get("playbook", {}).get("entries", []) if isinstance(dossier.get("playbook"), dict) else []
    lines = [
        "# ⚠️ ARET-MMU — REPRISE DÉGRADÉE : MÉMOIRE DE REPRISE INCOMPLÈTE",
        "Le dossier de reprise n'a PAS pu être construit complètement. NE POURSUIVEZ PAS comme si la reprise était normale : la barrière est active et la mémoire vivante est incomplète.",
        "\n## CE QUI MANQUE",
        *[f"- {item}" for item in dossier.get("errors", [])[:12]],
        "\n## LOIS STABLES (playbook — toujours autoritatives)" if entries else "\n## LOIS STABLES INDISPONIBLES — vérifier config/playbook.md",
    ]
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        domains = ", ".join(str(d) for d in entry.get("domains", []))
        lines.append(f"\n### {entry.get('title', '?')} [{domains}]")
        lines.append(str(entry.get("content", "")).strip())
    lines.extend([
        "\n## À FAIRE AVANT TOUTE AUTRE ACTION",
        "1. RÉPARER la mémoire (préparer un handoff via aret_prepare_handoff ; vérifier que config/playbook.md est présent et complet), OU",
        "2. reconnaître explicitement cet état dégradé pour poursuivre la réparation.",
        "\n## RITUEL DE CONFIRMATION OBLIGATOIRE",
        "RITUEL OBLIGATOIRE AVANT TOUTE POURSUITE : " + ritual_prompt(str(dossier.get("contract_hash", ""))),
        "Produisez le récapitulatif (les six volets — décrivez l'état DÉGRADÉ dans current_state) puis appelez aret_acknowledge_resume avec resume_contract_hash. La barrière PreToolUse refuse toute autre action jusque-là.",
    ])
    context = "\n".join(line for line in lines if line).strip()
    encoded = context.encode("utf-8")
    if len(encoded) > HOOK_CONTEXT_MAX_BYTES:
        context = encoded[:HOOK_CONTEXT_MAX_BYTES].decode("utf-8", "ignore")
    return context


def additional_context(result: dict[str, Any]) -> str:
    """Produit le dossier de reprise contractuel sans extrait arbitraire ni relecture Markdown.

    Quand le dossier n'est pas prêt, retourne un contexte DÉGRADÉ bruyant plutôt que de
    lever : le hook doit toujours injecter quelque chose et la barrière reste armée."""
    dossier = result.get("resume_dossier")
    if not isinstance(dossier, dict) or not dossier.get("ready"):
        return _degraded_additional_context(dossier if isinstance(dossier, dict) else {"errors": ["resume_dossier absent"]})
    playbook = dossier.get("playbook", {})
    entries = playbook.get("entries", []) if isinstance(playbook, dict) else []
    handoff = dossier.get("handoff", {}) if isinstance(dossier.get("handoff"), dict) else {}
    front = dossier.get("front", {}) if isinstance(dossier.get("front"), dict) else {}
    lines = [
        "# ARET-MMU — DOSSIER DE REPRISE CANONIQUE",
        "Ce dossier est dérivé de SQLite canonique, versionné, borné et contrôlé. Les documents métier historiques ne doivent pas être relus après compaction ; ne faites FIND/READ que pour approfondir une adresse précise nécessaire à la tâche.",
        f"Version du contrat : {dossier.get('contract_hash', '?')} ; préparation : {dossier.get('prepared_at', '?')}.",
        "\n## 1. PLAYBOOK STABLE — LOIS D’ARET",
    ]
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        domains = ", ".join(str(item) for item in entry.get("domains", []))
        lines.append(f"\n### {entry.get('title', '?')} [{domains}] — {entry.get('address', '?')}")
        lines.append(str(entry.get("content", "")).strip())

    lines.extend([
        "\n## 2. HANDOFF ACTIF — ÉTAT DU CHANTIER",
        *_front_lines(front),
        "\n### Résumé du travail réellement en cours",
        str(handoff.get("handoff_work_summary", "")),
        "\n### Résultats vérifiés",
        str(handoff.get("handoff_verified_results", "")),
        "\n### Risques ouverts",
        str(handoff.get("handoff_open_risks", "")),
        "\n### Dette sound et éléments différés",
        str(handoff.get("handoff_deferred_items", "")),
        "\n### Prochaine action atomique",
        str(handoff.get("next_action", "")),
        *_technical_checkpoint_lines(handoff),
        "\n## 3. ADRESSES PERTINENTES",
    ])
    addresses = front.get("relevant_addresses", []) if isinstance(front, dict) else []
    if isinstance(addresses, list) and addresses:
        lines.extend(f"- {address}" for address in addresses[:5])
    else:
        lines.append("- Aucune adresse chaude : préparer le handoff avant toute pause future.")

    catalog = result.get("pipeline_catalog", {})
    if isinstance(catalog, dict):
        lines.append("\n## 4. CAPACITÉS, OUTILS ET PORTES")
        lines.append("Pipelines fermés : dry_run=true est obligatoire avant toute opération GENERATE, NETWORK ou SENSITIVE.")
        for policy in ("READ_ONLY", "GENERATE", "NETWORK", "SENSITIVE"):
            names = catalog.get(policy, [])
            if isinstance(names, list) and names:
                lines.append(f"- {policy}: {', '.join(str(item) for item in names)}")
    toolchain = result.get("toolchain_status", {})
    if isinstance(toolchain, dict):
        tools = toolchain.get("tools", {})
        if isinstance(tools, dict):
            states = [
                f"{name}={'AVAILABLE' if isinstance(item, dict) and item.get('available') else 'UNAVAILABLE'}"
                for name, item in sorted(tools.items())
            ]
            lines.append("Toolchain observée : " + " ; ".join(states[:16]))
    lines.extend(_observation_lines(dossier))
    lines.append("GOUVERNANCE V1.4 : si une capacité ARET existe dans le catalogue MCP, utilisez-la plutôt qu’un équivalent shell. Le shell reste un laboratoire ; ses sorties ne sont ni faits canoniques ni preuves. Tout outil réutilisable ou contribuant de façon récurrente à une décision, validation, preuve, corpus, asset ou priorisation doit être industrialisé dans le MCP avant d’être déclaré capacité officielle.")
    lines.append("Outils MCP par capacité : " + _compact_tool_groups())

    git = result.get("git_context", {})
    lines.append("\n## 5. GIT, LIMITES ET GARDE-FOUS")
    if isinstance(git, dict):
        lines.append("Branche : " + str(git.get("branch", "unknown")))
        commits = git.get("recent_commits", [])
        if isinstance(commits, list) and commits:
            lines.append("Derniers commits : " + " | ".join(str(item) for item in commits[:8]))
        working_tree = git.get("working_tree", [])
        if isinstance(working_tree, list) and working_tree:
            lines.append("Arbre Git non propre : " + " | ".join(str(item) for item in working_tree[:12]))
    lines.append("FIND ne prouve rien ; READ récupère l’objet exact ; PROVEN exige une preuve PASS admissible. Aucun SQL, shell, URL ou push Git arbitraire n’est exposé. auto_push=false. Document 91 : NOT_APPLICABLE.")

    lines.extend([
        "\n## 6. RITUEL DE CONFIRMATION OBLIGATOIRE",
        "RITUEL OBLIGATOIRE AVANT TOUTE POURSUITE : " + ritual_prompt(str(dossier.get("contract_hash", ""))),
        "Produisez le récapitulatif dans votre réponse de reprise puis appelez aret_acknowledge_resume avec les six champs et resume_contract_hash. La barrière PreToolUse refusera toute autre action jusque-là.",
    ])
    context = "\n".join(line for line in lines if line).strip()
    size = len(context.encode("utf-8"))
    if size > HOOK_CONTEXT_MAX_BYTES:
        raise AretError(f"Resume Dossier dépasse la borne de transport de {HOOK_CONTEXT_MAX_BYTES} octets ({size})")
    return context


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
