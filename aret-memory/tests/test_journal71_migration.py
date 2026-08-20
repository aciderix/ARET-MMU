from __future__ import annotations

import hashlib
from pathlib import Path

from core.repository import MemoryStore
from migration.import_journal_71 import JOURNAL_PATH, parse_journal, run


def test_journal71_parse_and_full_import_are_exact_and_idempotent(tmp_path: Path) -> None:
    aret_repo = Path(__file__).resolve().parents[2]
    entries = parse_journal(aret_repo)
    assert len(entries) == 378
    assert entries[0].start_line == 382
    assert entries[-1].end_line == 8719
    assert all(entry.content.startswith("### ") for entry in entries)
    assert all(entry.source_hash == hashlib.sha256(entry.content.encode("utf-8")).hexdigest() for entry in entries)

    memory_dir = tmp_path / ".aret-memory"
    first = run(aret_repo, memory_dir)
    assert len(first["imported"]) == len(entries)
    assert first["skipped_existing"] == []
    assert sum(first["classification"].values()) == len(entries)

    store = MemoryStore(memory_dir, write_enabled=False)
    with store._read_connection() as conn:
        source_count = conn.execute("SELECT COUNT(*) FROM knowledge_source WHERE source_path=?", (JOURNAL_PATH,)).fetchone()[0]
        knowledge_count = conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
        batch_status = conn.execute("SELECT status FROM migration_batch WHERE id=?", (first["migration_batch_id"],)).fetchone()[0]
    assert source_count == len(entries)
    assert knowledge_count == len(entries)
    assert batch_status == "COMPLETED"

    latest = store.read("ARET://knowledge/RECOV-0001")
    provenance = latest["sources"][0]
    source = aret_repo / provenance["source_path"]
    raw_lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
    expected = "".join(raw_lines[provenance["source_start_line"] - 1 : provenance["source_end_line"]]).rstrip("\n")
    assert latest["content"] == expected
    assert provenance["source_hash"] == hashlib.sha256(expected.encode("utf-8")).hexdigest()
    assert store.get_front()["state"]["journal_71_entry_count"]["value"] == str(len(entries))

    second = run(aret_repo, memory_dir)
    assert second["imported"] == []
    assert len(second["skipped_existing"]) == len(entries)
