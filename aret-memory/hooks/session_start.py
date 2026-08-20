"""Hook SessionStart : injecte le paquet SQLite de reprise et arme le rituel."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from common import repository_context, run
from evidence.adapters.pipelines import pipeline_catalog, toolchain_status
from resume_guard import arm, ritual_prompt


def handler(store: Any, payload: dict[str, Any]) -> dict[str, Any]:
    context = store.get_resume_context(journal_limit=8, rule_limit=12, excerpt_bytes=260)
    guard = arm(store.memory_dir, payload, reason="SessionStart")
    catalog = pipeline_catalog()
    pipeline_summary = {
        policy: [item["name"] for item in items]
        for policy, items in catalog["policies"].items()
    }
    return {
        **context,
        "git_context": repository_context(),
        "resume_guard": {
            "armed_at": guard["armed_at"],
            "reason": guard["reason"],
            "status": guard["status"],
            "required_sections": guard["required_fields"],
        },
        "resume_ritual": {
            "required": True,
            "tool": "aret_acknowledge_resume",
            "prompt": ritual_prompt(),
        },
        "pipeline_catalog": pipeline_summary,
        "toolchain_status": toolchain_status(Path(__file__).resolve().parents[2]),
        "recent_pipeline_runs": store.get_pipeline_runs(limit=8)["runs"],
        "pipeline_contract": catalog["contract"],
        "instructions": [
            "Le contexte critique est déjà injecté depuis SQLite ; ne relire un document source que pour un approfondissement ciblé.",
            "Avant toute poursuite, produire le récapitulatif rituel des règles, état, capacités, Git, limites et prochaine action.",
            "Confirmer ce récapitulatif par aret_acknowledge_resume ; PreToolUse bloque toute autre opération jusqu’à cette confirmation.",
            "Utiliser FIND uniquement pour découvrir ; READ/READ_BATCH pour un objet précis ; ne jamais assimiler un score à une preuve.",
            "Consulter le catalogue pipeline avant toute action et utiliser dry_run=true avant génération, réseau ou opération sensible.",
        ],
    }


if __name__ == "__main__":
    run("SessionStart", handler)
