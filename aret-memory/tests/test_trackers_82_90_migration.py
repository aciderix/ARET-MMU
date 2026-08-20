from __future__ import annotations

from pathlib import Path

from core.repository import MemoryStore
from migration.import_trackers_82_90 import DOCUMENTS, parse_all, run
from migration.verify_trackers_82_90 import verify


def test_trackers_82_90_import_is_exact_and_idempotent(tmp_path: Path) -> None:
    aret_repo = Path(__file__).resolve().parents[2]
    sections = parse_all(aret_repo)
    assert len(sections) == 50
    assert sum(item.path == DOCUMENTS[0] for item in sections) == 33
    assert sum(item.path == DOCUMENTS[1] for item in sections) == 17
    assert all(item.content.startswith("##") for item in sections)

    memory_dir = tmp_path / ".aret-memory"
    first = run(aret_repo, memory_dir)
    assert len(first["imported"]) == len(sections)
    assert first["skipped_existing"] == []

    report = verify(aret_repo, memory_dir)
    assert report["ok"] is True
    assert report["actual_counts"][DOCUMENTS[0]] == 33
    assert report["actual_counts"][DOCUMENTS[1]] == 17

    store = MemoryStore(memory_dir, write_enabled=False)
    front = store.get_front()["state"]
    assert front["migration_trackers_82_count"]["value"] == "33"
    assert front["migration_corpus_90_count"]["value"] == "17"

    second = run(aret_repo, memory_dir)
    assert second["imported"] == []
    assert len(second["skipped_existing"]) == len(sections)
