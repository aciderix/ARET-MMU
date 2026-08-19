from __future__ import annotations

import sqlite3

from core.repository import MemoryStore


def test_relation_supersession_is_append_only_and_audited(tmp_path) -> None:
    store = MemoryStore(tmp_path / ".aret-memory", write_enabled=True)
    store.register_component("CORE", "Core", "", "test")
    store.register_brick("BRICK-1", "Brique", "PLANNED", "CORE", "", "test")
    original = store.add_relation("CORE", "CONCERNS", "BRICK-1", "test")
    result = store.supersede_relation(
        original["id"], "CORE", "IMPLEMENTS", "BRICK-1", "test"
    )

    assert result["superseded_relation"] == original["address"]
    assert result["replacement"]["relation_type"] == "IMPLEMENTS"
    with sqlite3.connect(store.db_path) as connection:
        relations = connection.execute("SELECT relation_type FROM relation ORDER BY created_at, id").fetchall()
        audit = connection.execute(
            "SELECT operation, entity_id, payload_after FROM audit_event WHERE operation='SUPERSEDE_RELATION'"
        ).fetchone()

    assert [row[0] for row in relations] == ["CONCERNS", "IMPLEMENTS"]
    assert audit is not None
    assert audit[0] == "SUPERSEDE_RELATION"
    assert audit[1] == original["id"]
    assert result["replacement"]["id"] in audit[2]
