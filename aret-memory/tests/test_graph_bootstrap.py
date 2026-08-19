from __future__ import annotations

from core.repository import MemoryStore
from migration import bootstrap_initial_graph as bootstrap


def append_forensic(store: MemoryStore, title: str, content: str) -> dict[str, object]:
    return store.append_knowledge(
        knowledge_type="FORENSIC", status="OBSERVED", title=title, content=content,
        component_id="CORE", function_id=None, brick_id=None, tags=["TEST"], proof_ids=[],
        supersedes_id=None, actor="test",
    )


def test_bootstrap_creates_literal_concerns_and_replaces_front_idempotently(tmp_path, monkeypatch) -> None:
    store = MemoryStore(tmp_path / ".aret-memory", write_enabled=True)
    store.register_component("CORE", "Noyau", "", "test")
    cited = append_forensic(store, "Alpha", "Le symbole alpha_fn est attesté.")
    uncited = append_forensic(store, "Bêta", "Aucune occurrence recherchée.")
    store.update_front({"subsystem": "migration", "obsolete_key": "à retirer"}, "test")

    monkeypatch.setattr(bootstrap, "FUNCTIONS", (
        {"component_id": "CORE", "module": "test", "symbol": "alpha_fn", "calling_convention": "cdecl"},
    ))
    monkeypatch.setattr(bootstrap, "BRICKS", ())
    monkeypatch.setattr(bootstrap, "CURATED_SUPERSEDES", ())
    monkeypatch.setattr(bootstrap, "FRONT", {
        "subsystem": "ingénierie", "relevant_1_address": cited["address"],
    })

    first = bootstrap.bootstrap(store)
    second = bootstrap.bootstrap(store)

    function_id = "CORE:test!alpha_fn"
    assert first["counts"] == {"functions_created": 1, "bricks_created": 0, "concerns_created": 1, "supersedes_created": 0}
    assert first["concerns_created"][0]["knowledge_id"] == cited["id"]
    assert first["concerns_created"][0]["function_id"] == function_id
    assert second["counts"] == {"functions_created": 0, "bricks_created": 0, "concerns_created": 0, "supersedes_created": 0}
    assert store.get_related(cited["id"], "CONCERNS", "outgoing")["relations"][0]["to_id"] == function_id
    assert store.get_related(uncited["id"], "CONCERNS", "outgoing")["relations"] == []
    front = store.get_front()["state"]
    assert front["subsystem"]["value"] == "ingénierie"
    assert "obsolete_key" not in front
    assert any(event["operation"] == "REPLACE_FRONT" for event in store.audit_events())
