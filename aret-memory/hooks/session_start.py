"""Hook SessionStart : restitue le contrat minimal de reprise, sans mutation."""

from __future__ import annotations

from typing import Any

from common import repository_context, run
from evidence.adapters.pipelines import pipeline_catalog
from resume_guard import arm


def handler(store: Any, payload: dict[str, Any]) -> dict[str, Any]:
    brief = store.get_resume_brief()
    protocol = store.get_resume_protocol()
    guard = arm(store.memory_dir, payload, protocol["required_addresses"], reason="SessionStart")
    protocol_summary = {
        "protocol_version": protocol["protocol_version"], "required_address_count": protocol["required_address_count"],
        "batch_count": protocol["batch_count"], "instructions": protocol["instructions"],
    }
    restored = brief.pop("restore")
    catalog = pipeline_catalog()
    recent_runs = store.get_pipeline_runs(limit=8)["runs"]
    pipeline_summary = {
        policy: [item["name"] for item in items]
        for policy, items in catalog["policies"].items()
    }
    return {
        **restored,
        "rules": brief["rules"],
        "latest_document_71_entries": brief["latest_document_71_entries"],
        "recent_audit": brief["recent_audit"],
        "git_context": repository_context(),
        "resume_notice": brief["notice"],
        "resume_protocol": protocol_summary,
        "resume_guard": {
            "armed_at": guard["armed_at"], "reason": guard["reason"],
            "remaining_address_count": len(guard["remaining_addresses"]),
        },
        "pipeline_catalog": pipeline_summary,
        "recent_pipeline_runs": recent_runs,
        "pipeline_contract": catalog["contract"],
        "instructions": [
            "Utiliser FIND uniquement pour découvrir des candidats.",
            "Utiliser READ ou READ_BATCH pour récupérer les objets canoniques explicitement adressés.",
            "Ne jamais traiter un score de recherche comme une preuve.",
            "Consulter le catalogue pipeline avant une action ; lancer aret_run_pipeline avec dry_run=true avant toute exécution générative, réseau ou sensible.",
            "Barrière de reprise active : lire tous les lots de resume_protocol via aret_read_batch avant toute opération non liée à la reprise. PreToolUse bloque toute autre action tant que les lectures ne sont pas complètes.",
        ],
    }


if __name__ == "__main__":
    run("SessionStart", handler)
