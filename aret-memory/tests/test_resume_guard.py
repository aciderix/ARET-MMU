from __future__ import annotations

from pathlib import Path

from core.repository import MemoryStore
from hooks.resume_guard import acknowledge, arm, decision, stop_feedback, validate_recap


RESUME_HASH = "a" * 64
PLAYBOOK_PADDING = (
    " Cette entrée contractuelle s’applique à chaque incrément, doit être vérifiée par une preuve "
    "reproductible et interdit toute valeur devinée, tout succès silencieux ou toute conclusion non auditée."
)

PLAYBOOK = (
    ("PLAYBOOK_FOUNDATION", "Principe sound", "Juste ou arrêt bruyant, jamais de valeur inventée ni de faux succès silencieux."),
    ("PLAYBOOK_METHOD", "Méthode", "Mesurer, reproduire, fixture minimale, implémenter, vérifier puis documenter."),
    ("PLAYBOOK_ARCHITECTURE", "Architecture", "Wine est une source et un oracle, jamais une dépendance runtime ; le modèle shared-stack reste sound."),
    ("PLAYBOOK_GATES", "Portes", "Les oracles appropriés et les hashes requis valident chaque changement pertinent."),
    ("PLAYBOOK_TOOLING", "Outils", "Trace, relay, wallsweep et pipelines fermés servent à mesurer avant toute modification."),
)


def _populated_store(memory_dir: Path) -> MemoryStore:
    store = MemoryStore(memory_dir, write_enabled=True)
    store.register_component("CORE", "Noyau", "Fixture de reprise", "test")
    store.register_brick("RESUME-01", "Brique de reprise", "ACTIVE", "CORE", "Fixture", "test", "M1", "x86-pe32", 1)
    addresses: list[str] = []
    for domain, title, content in PLAYBOOK:
        tags = ["CORE_PLAYBOOK", domain]
        if domain == "PLAYBOOK_ARCHITECTURE":
            tags.append("PLAYBOOK_SHARED_STACK")
        record = store.append_knowledge(
            knowledge_type="ARCHITECTURE" if domain == "PLAYBOOK_ARCHITECTURE" else "RULE",
            status="ACTIVE", title=title, content=content + PLAYBOOK_PADDING, component_id="CORE", function_id=None,
            brick_id=None, tags=tags, proof_ids=[], supersedes_id=None, actor="test",
        )
        addresses.append(record["address"])
    store.update_front({
        "subsystem": "Fixture", "brick": "RESUME-01", "current_wall": "Validation de reprise",
        "last_action": "Playbook V5 tagué.", "next_action": "Confirmer le rituel de reprise.",
        "relevant_1_address": addresses[0],
    }, "test")
    store.prepare_handoff(
        work_summary="Le playbook stable est prêt et le contexte métier actif est explicitement préparé.",
        verified_results="Les connaissances de fixture et le Front ont été écrits dans SQLite avec audit.",
        open_risks="Aucun risque bloquant connu ; toute divergence doit interrompre la reprise.",
        deferred_items="Aucun élément différé ne doit masquer une action de reprise critique.",
        next_action="Produire le récapitulatif puis confirmer le rituel avec le dossier injecté.",
        technical_checkpoint_state="NONE",
        relevant_addresses=addresses[:2], actor="test",
    )
    return store


def _recap(contract_hash: str = RESUME_HASH) -> dict[str, str]:
    return {
        "working_rules": "Le playbook injecté impose le correct ou arrêt bruyant, la preuve avant affirmation et la méthode mesurer puis vérifier.",
        "current_state": "Le handoff injecté fixe le Front, l’état actif, les résultats vérifiés, les risques et le prochain incrément.",
        "capabilities": "Les outils MCP, oracles, assets et pipelines fermés sont disponibles ; un dry run précède toute action générative, réseau ou sensible.",
        "git_state": "La branche active, les derniers commits et l’état de l’arbre ont été examinés dans le contexte de reprise automatiquement injecté.",
        "risks_and_limits": "Une recherche ne prouve rien, aucun SQL ou shell arbitraire n’est permis, auto_push reste faux et le document 91 est non applicable.",
        "next_action": "Je vais confirmer le point de départ avec le Front et exécuter ensuite une action ciblée conforme aux limites et priorités injectées.",
        "resume_contract_hash": contract_hash,
    }


def test_resume_context_requires_a_complete_sqlite_dossier_without_document_reread(tmp_path: Path) -> None:
    context = _populated_store(tmp_path / "memory").get_resume_context()
    dossier = context["resume_dossier"]

    assert dossier["ready"] is True
    assert dossier["playbook"]["domains"] == [
        "PLAYBOOK_FOUNDATION", "PLAYBOOK_METHOD", "PLAYBOOK_ARCHITECTURE", "PLAYBOOK_GATES", "PLAYBOOK_TOOLING",
    ]
    assert dossier["handoff"]["next_action"].startswith("Produire le récapitulatif")
    assert "document source ne doit être relu" in context["notice"]
    assert "rules" not in context


def test_resume_guard_blocks_until_a_complete_ritual_recap_is_acknowledged(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    session = {"session_id": "test-resume"}
    armed = arm(memory_dir, session, reason="SessionStart", resume_contract_hash=RESUME_HASH)
    assert armed["status"] == "awaiting_recap"

    blocked = decision(memory_dir, {**session, "tool_name": "Bash", "tool_input": {"command": "true"}})
    assert blocked is not None
    assert blocked["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "ne relisez pas les documents source" in blocked["hookSpecificOutput"]["additionalContext"]
    assert RESUME_HASH in blocked["hookSpecificOutput"]["additionalContext"]
    assert decision(memory_dir, {**session, "tool_name": "mcp__aret-memory__aret_acknowledge_resume", "tool_input": _recap()}) is None

    rejected = acknowledge(memory_dir, {
        **session,
        "tool_name": "mcp__aret-memory__aret_acknowledge_resume",
        "tool_input": _recap("b" * 64),
        "tool_response": {"structuredContent": {"ok": True}},
    })
    assert rejected is not None
    assert rejected["acknowledged_at"] is None

    completed = acknowledge(memory_dir, {
        **session,
        "tool_name": "mcp__aret-memory__aret_acknowledge_resume",
        "tool_input": _recap(),
        "tool_response": {"structuredContent": {"ok": True}},
    })
    assert completed is not None
    assert completed["acknowledged_at"] is not None
    assert completed["recap"]["next_action"] == _recap()["next_action"]
    assert decision(memory_dir, {**session, "tool_name": "Edit", "tool_input": {}}) is None


def test_resume_guard_keeps_barrier_for_an_incomplete_recap_and_stop_is_single_shot(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    session = {"session_id": "test-stop"}
    arm(memory_dir, session, reason="PostCompact", resume_contract_hash=RESUME_HASH)
    incomplete = {**_recap(), "next_action": "trop court"}
    try:
        validate_recap(incomplete)
    except ValueError as exc:
        assert "prochaine action proposée" in str(exc)
    else:
        raise AssertionError("Le récapitulatif incomplet doit être refusé")

    feedback = stop_feedback(memory_dir, session)
    assert feedback is not None
    assert "ne relisez pas les documents source" in feedback["hookSpecificOutput"]["additionalContext"]
    assert stop_feedback(memory_dir, {**session, "stop_hook_active": True}) is None
