from __future__ import annotations

from pathlib import Path

from core.repository import MemoryStore
from hooks.resume_guard import arm, decision, mark_read, stop_feedback


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
            knowledge_type="RULE", status="ACTIVE", title=f"Page {index}", content="Contenu canonique.",
            component_id="CORE", function_id=None, brick_id=None, tags=["RULE"], proof_ids=[], supersedes_id=None,
            actor="test", document_source=_source(path, index * 10),
        )
    for index in (100, 200):
        store.append_knowledge(
            knowledge_type="MEASUREMENT", status="OBSERVED", title=f"Journal {index}", content="Entrée canonique.",
            component_id="CORE", function_id=None, brick_id=None, tags=["JOURNAL"], proof_ids=[], supersedes_id=None,
            actor="test", document_source=_source(JOURNAL, index),
        )
    return store


def test_resume_protocol_requires_all_canonical_documents_and_recent_journal(tmp_path: Path) -> None:
    protocol = _populated_store(tmp_path / "memory").get_resume_protocol(journal_limit=2, batch_size=3)

    assert tuple(protocol["mandatory_documents"]) == DOCUMENTS
    assert all(len(protocol["mandatory_documents"][path]) == 1 for path in DOCUMENTS)
    assert [entry["source_start_line"] for entry in protocol["latest_document_71_entries"]] == [200, 100]
    assert protocol["required_address_count"] == 7
    assert protocol["batch_count"] == 3
    assert sum(len(batch) for batch in protocol["required_read_batches"]) == 7


def test_resume_guard_allows_only_protocol_and_reads_until_every_address_is_read(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    required = ["ARET://knowledge/CORE-0001", "ARET://knowledge/CORE-0002"]
    session = {"session_id": "test-resume"}
    arm(memory_dir, session, required, reason="SessionStart")

    blocked = decision(memory_dir, {**session, "tool_name": "Bash", "tool_input": {"command": "true"}})
    assert blocked is not None
    assert blocked["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert decision(memory_dir, {**session, "tool_name": "mcp__aret-memory__aret_get_resume_protocol", "tool_input": {}}) is None

    mark_read(memory_dir, {
        **session, "tool_name": "mcp__aret-memory__aret_read_batch",
        "tool_input": {"addresses": [required[0]]}, "tool_response": {"structuredContent": {"ok": True}},
    })
    assert decision(memory_dir, {**session, "tool_name": "Edit", "tool_input": {}}) is not None

    completed = mark_read(memory_dir, {
        **session, "tool_name": "mcp__aret-memory__aret_read_batch",
        "tool_input": {"addresses": [required[1]]}, "tool_response": {"structuredContent": {"ok": True}},
    })
    assert completed is not None
    assert completed["remaining_addresses"] == []
    assert completed["completed_at"] is not None
    assert decision(memory_dir, {**session, "tool_name": "Edit", "tool_input": {}}) is None


def test_resume_guard_stop_feedback_is_single_shot(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    session = {"session_id": "test-stop"}
    arm(memory_dir, session, ["ARET://knowledge/CORE-0001"], reason="PostCompact")

    feedback = stop_feedback(memory_dir, session)
    assert feedback is not None
    assert "aret_get_resume_protocol" in feedback["hookSpecificOutput"]["additionalContext"]
    assert stop_feedback(memory_dir, {**session, "stop_hook_active": True}) is None
