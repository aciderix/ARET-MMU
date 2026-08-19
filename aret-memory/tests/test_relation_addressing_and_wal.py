from __future__ import annotations

from pathlib import Path

from core.repository import MemoryStore
from ops.git_memory import checkpoint_wal


def test_relation_address_is_readable_through_canonical_read(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / ".aret-memory", write_enabled=True)
    store.register_component("CORE", "Noyau", "", "test")
    store.register_brick("BRICK-1", "Brique", "PLANNED", "CORE", "", "test")

    relation = store.add_relation("CORE", "CONCERNS", "BRICK-1", "test")
    read_back = store.read(relation["address"])

    assert relation["address"] == "ARET://relation/R-0001"
    assert read_back["address"] == relation["address"]
    assert read_back["from_id"] == "CORE"
    assert read_back["relation_type"] == "CONCERNS"
    assert read_back["to_id"] == "BRICK-1"


def test_export_bundle_reports_successful_wal_checkpoint(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / ".aret-memory", write_enabled=True)
    store.register_component("CORE", "Noyau", "", "test")

    bundle = store.export_bundle("wal-checkpoint")

    assert bundle["wal_checkpoint"]["busy"] == 0
    assert bundle["wal_checkpoint"]["checkpointed_frames"] >= 0


def test_git_wal_checkpoint_consolidates_existing_memory_database(tmp_path: Path) -> None:
    memory_dir = tmp_path / "aret-memory" / ".aret-memory"
    store = MemoryStore(memory_dir, write_enabled=True)
    store.register_component("CORE", "Noyau", "", "test")

    result = checkpoint_wal(memory_dir)

    assert result["checkpointed"] is True
    assert result["busy"] == 0
