from __future__ import annotations

import hashlib
from pathlib import Path

from core.repository import MemoryStore
from migration.import_pilot import PILOT_SLICES, run


def test_pilot_migration_is_sourced_and_idempotent(tmp_path: Path) -> None:
    aret_repo = Path(__file__).resolve().parents[2]
    memory_dir = tmp_path / ".aret-memory"
    first = run(aret_repo, memory_dir)
    assert len(first["imported"]) == len(PILOT_SLICES)
    assert first["skipped_existing"] == []
    assert first["migration_batch_id"].startswith("MIG-PILOT-")

    store = MemoryStore(memory_dir, write_enabled=False)
    with store._read_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0] == len(PILOT_SLICES)
        assert conn.execute("SELECT COUNT(*) FROM knowledge_source").fetchone()[0] == len(PILOT_SLICES)
        batch = conn.execute("SELECT status, source_revision, summary_json FROM migration_batch").fetchone()
    assert batch["status"] == "COMPLETED"
    assert batch["source_revision"] == first["revision"]

    sample = store.read("ARET://knowledge/RECOV-0001")
    assert sample["effective_at"] == "2026-08-17"
    assert len(sample["sources"]) == 1
    source = sample["sources"][0]
    origin = aret_repo / source["source_path"]
    raw_lines = origin.read_text(encoding="utf-8").splitlines(keepends=True)
    exact_text = "".join(raw_lines[source["source_start_line"] - 1 : source["source_end_line"]]).rstrip("\n")
    assert sample["content"] == exact_text
    assert source["source_hash"] == hashlib.sha256(exact_text.encode("utf-8")).hexdigest()

    front = store.get_front()
    assert front["state"]["brick"]["value"] == "MIGRATION-PILOT-01"
    assert "ARET://knowledge/RECOV-0001" in front["relevant_addresses"]

    second = run(aret_repo, memory_dir)
    assert second["imported"] == []
    assert len(second["skipped_existing"]) == len(PILOT_SLICES)
    with store._read_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0] == len(PILOT_SLICES)
