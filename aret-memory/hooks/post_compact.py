"""Hook PostCompact : réinjecte le paquet SQLite de reprise et réarme le rituel."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from common import repository_context
from evidence.adapters.pipelines import pipeline_catalog, toolchain_status
from resume_guard import arm, ritual_prompt


def handler(store: Any, payload: dict[str, Any]) -> dict[str, Any]:
    context = store.get_resume_context(journal_limit=8, rule_limit=12, excerpt_bytes=260)
    dossier_hash = context["resume_dossier"]["contract_hash"]
    guard = arm(store.memory_dir, payload, reason="PostCompact", resume_contract_hash=dossier_hash)
    checkpoint = None
    if store.write_enabled:
        checkpoint = store.record_session_checkpoint(
            "POST_COMPACT", payload.get("session_id"), payload.get("trigger"), payload.get("compact_summary"), "aret-hook-postcompact"
        )
    catalog = pipeline_catalog()
    return {
        **context,
        "relevant_addresses": context["front"]["relevant_addresses"],
        "git_context": repository_context(),
        "checkpoint": checkpoint,
        "resume_guard": {
            "armed_at": guard["armed_at"],
            "reason": guard["reason"],
            "status": guard["status"],
            "required_sections": guard["required_fields"],
            "resume_contract_hash": guard["resume_contract_hash"],
        },
        "resume_ritual": {
            "required": True,
            "tool": "aret_acknowledge_resume",
            "prompt": ritual_prompt(dossier_hash),
        },
        "pipeline_catalog": {policy: [item["name"] for item in items] for policy, items in catalog["policies"].items()},
        "toolchain_status": toolchain_status(Path(__file__).resolve().parents[2]),
        "recent_pipeline_runs": store.get_pipeline_runs(limit=8)["runs"],
        "notice": "PostCompact a réinjecté le contexte SQLite et armé le récapitulatif rituel. Aucun document source n’est à relire par défaut ; produisez le récapitulatif puis confirmez-le avec aret_acknowledge_resume avant de poursuivre.",
    }


if __name__ == "__main__":
    from common import run

    run("PostCompact", handler)
