from __future__ import annotations

from core.repository import MemoryStore


def test_superseded_relation_is_hidden_by_default_and_readable_in_history(tmp_path) -> None:
    store = MemoryStore(tmp_path / ".aret-memory", write_enabled=True)
    store.register_component("CORE", "Noyau", "", "test")
    store.register_brick("BRICK-A", "A", "PLANNED", "CORE", "", "test")
    store.register_brick("BRICK-B", "B", "PLANNED", "CORE", "", "test")
    original = store.add_relation("CORE", "CONCERNS", "BRICK-A", "test")

    result = store.supersede_relation(original["id"], "CORE", "CONCERNS", "BRICK-B", "test")

    old = store.read(original["address"])
    replacement = store.read(result["replacement"]["address"])
    active = store.get_related("CORE", "CONCERNS", "outgoing")
    historical = store.get_related("CORE", "CONCERNS", "outgoing", include_inactive=True)

    assert old["status"] == "SUPERSEDED"
    assert old["superseded_by"] == replacement["id"]
    assert replacement["status"] == "ACTIVE"
    assert [row["id"] for row in active["relations"]] == [replacement["id"]]
    assert {row["id"] for row in historical["relations"]} == {original["id"], replacement["id"]}
