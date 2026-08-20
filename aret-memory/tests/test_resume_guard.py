from __future__ import annotations

from pathlib import Path

from core.repository import MemoryStore
from hooks.resume_guard import acknowledge, arm, decision, stop_feedback, validate_recap


DOCUMENTS = (
    "docs/vision/70-reference-etat-methode-reste.md",
    "docs/vision/80-orientations-architecturales.md",
    "docs/vision/81-industrialisation.md",
    "docs/vision/82-suivi-industrialisation.md",
    "docs/vision/90-corpus-sources.md",
)
JOURNAL = "docs/vision/71-journal-de-bord.md"


def _source(path: str, line: int) -> dict[str, object]:
    return {
        "repository": "aciderix/ARET",
        "revision": "a" * 40,
        "path": path,
        "start_line": line,
        "end_line": line + 1,
        "section": f"§{line}",
        "hash": "b" * 64,
    }


def _populated_store(memory_dir: Path) -> MemoryStore:
    store = MemoryStore(memory_dir, write_enabled=True)
    store.register_component("CORE", "Noyau", "Fixture de reprise", "test")
    for index, path in enumerate(DOCUMENTS, start=1):
        store.append_knowledge(
            knowledge_type="RULE", status="ACTIVE", title=f"Règle {index}",
            content=f"Règle canonique {index} : correct ou arrêt bruyant, jamais de faux succès silencieux.",
            component_id="CORE", function_id=None, brick_id=None, tags=["RULE"], proof_ids=[], supersedes_id=None,
            actor="test", document_source=_source(path, index * 10),
        )
    for index in (100, 200):
        store.append_knowledge(
            knowledge_type="MEASUREMENT", status="OBSERVED", title=f"Journal {index}",
            content=f"Évolution canonique {index} : état de l’industrialisation mis à jour.",
            component_id="CORE", function_id=None, brick_id=None, tags=["JOURNAL"], proof_ids=[], supersedes_id=None,
            actor="test", document_source=_source(JOURNAL, index),
        )
    return store


def _recap() -> dict[str, str]:
    return {
        "working_rules": "Les règles injectées imposent la séparation FIND puis READ, l’honnêteté des verdicts et une preuve PASS admissible pour PROVEN.",
        "current_state": "Le Front, la roadmap et les derniers changements injectés fixent l’état actif, les bloqueurs et le contexte de la prochaine intervention.",
        "capabilities": "Les outils MCP, oracles, assets et pipelines fermés sont disponibles ; un dry run précède toute action générative, réseau ou sensible.",
        "git_state": "La branche active, les derniers commits et l’état de l’arbre ont été examinés dans le contexte de reprise automatiquement injecté.",
        "risks_and_limits": "Une recherche ne prouve rien, aucun SQL ou shell arbitraire n’est permis, auto_push reste faux et le document 91 est non applicable.",
        "next_action": "Je vais confirmer le point de départ avec le Front et exécuter ensuite une action ciblée conforme aux limites et priorités injectées.",
    }


def test_resume_context_injects_sqlite_excerpts_without_requiring_document_reread(tmp_path: Path) -> None:
    context = _populated_store(tmp_path / "memory").get_resume_context(journal_limit=2, rule_limit=8, excerpt_bytes=220)

    assert len(context["rules"]) == 5
    assert all(item["content_excerpt"].startswith("Règle canonique") for item in context["rules"])
    assert [entry["source_start_line"] for entry in context["latest_document_71_entries"]] == [200, 100]
    assert all(item["content_excerpt"].startswith("Évolution canonique") for item in context["latest_document_71_entries"])
    assert "aucun document source" in context["notice"]
    assert "required_read_batches" not in context


def test_resume_guard_blocks_until_a_complete_ritual_recap_is_acknowledged(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    session = {"session_id": "test-resume"}
    armed = arm(memory_dir, session, reason="SessionStart")
    assert armed["status"] == "awaiting_recap"

    blocked = decision(memory_dir, {**session, "tool_name": "Bash", "tool_input": {"command": "true"}})
    assert blocked is not None
    assert blocked["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "ne relisez pas les documents source" in blocked["hookSpecificOutput"]["additionalContext"]
    assert decision(memory_dir, {**session, "tool_name": "mcp__aret-memory__aret_acknowledge_resume", "tool_input": _recap()}) is None

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
    arm(memory_dir, session, reason="PostCompact")
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
