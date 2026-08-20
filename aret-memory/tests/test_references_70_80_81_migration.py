from __future__ import annotations

from pathlib import Path

from core.repository import MemoryStore
from migration.import_pilot import git_revision
from migration.import_references_70_80_81 import DOCUMENTS, parse_for_store, run
from migration.verify_references_70_80_81 import verify


def test_references_70_80_81_are_covered_and_idempotent(tmp_path: Path) -> None:
    aret_repo = Path(__file__).resolve().parents[2]
    memory_dir = tmp_path / ".aret-memory"
    writable_store = MemoryStore(memory_dir, write_enabled=True)
    sections = parse_for_store(aret_repo, writable_store, git_revision(aret_repo))
    assert sections
    assert {item.path for item in sections} == set(DOCUMENTS)
    assert all(item.content.startswith("##") or item.content.startswith("###") for item in sections)

    first = run(aret_repo, memory_dir)
    assert len(first["imported"]) == len(sections)
    assert first["skipped_existing"] == []

    report = verify(aret_repo, memory_dir)
    assert report["ok"] is True
    assert all(report["actual_counts"][path] > 0 for path in DOCUMENTS)

    store = MemoryStore(memory_dir, write_enabled=False)
    with store._read_connection() as conn:
        statuses = [row[0] for row in conn.execute(
            "SELECT DISTINCT k.status FROM knowledge k JOIN knowledge_source s ON s.knowledge_id=k.id WHERE s.source_path IN (?, ?, ?)",
            DOCUMENTS,
        )]
    assert "PROVEN" not in statuses

    second = run(aret_repo, memory_dir)
    assert second["imported"] == []
    assert second["skipped_existing"] == []
