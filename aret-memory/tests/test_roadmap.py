from __future__ import annotations

import pytest

from core.repository import AretError, MemoryStore


def build_store(tmp_path) -> MemoryStore:
    store = MemoryStore(tmp_path / ".aret-memory", write_enabled=True)
    store.register_component("CORE", "Core", "", "test")
    store.register_brick("TARGET-WASM-01", "Backend WASM", "ACTIVE", "CORE", "", "test", "M8", "wasm32-wasi", 1)
    store.register_brick("TARGET-WASM-02", "Runtime WASM", "PLANNED", "CORE", "", "test", "M8", "wasm32-wasi", 2)
    store.register_brick("TARGET-WASM-03", "Corpus WASM", "DONE", "CORE", "", "test", "M8", "wasm32-wasi", 3)
    store.add_relation("TARGET-WASM-01", "BLOCKED_BY", "TARGET-WASM-02", "test")
    store.add_relation("TARGET-WASM-01", "IMPLEMENTS", "CORE", "test")
    return store


def test_roadmap_filters_active_relations_and_export(tmp_path) -> None:
    store = build_store(tmp_path)

    roadmap = store.get_roadmap(milestone="M8", target_platform="wasm32-wasi")

    assert [brick["id"] for brick in roadmap["bricks"]] == ["TARGET-WASM-01", "TARGET-WASM-02"]
    assert roadmap["summary"]["active"] == 1
    assert roadmap["summary"]["planned"] == 1
    assert roadmap["summary"]["done"] == 0
    active = roadmap["bricks"][0]
    assert active["blockers"][0]["address"] == "ARET://brick/TARGET-WASM-02"
    assert active["implements"][0]["address"] == "ARET://component/CORE"

    exported = store.export_roadmap(milestone="M8", target_platform="wasm32-wasi", output_name="wasm")
    content = (store.exports_dir / "wasm.md").read_text(encoding="utf-8")
    assert exported["brick_count"] == 2
    assert exported["logical_view_hash"] == roadmap["logical_view_hash"]
    assert "TARGET-WASM-01" in content
    assert "TARGET-WASM-03" not in content


def test_roadmap_metadata_and_front_state_machine_are_validated(tmp_path) -> None:
    store = build_store(tmp_path)
    store.replace_front({"brick": "TARGET-WASM-01", "subsystem": "WASM"}, "test")

    with pytest.raises(AretError, match="ACTIVE"):
        store.update_front({"brick": "TARGET-WASM-02"}, "test")
    with pytest.raises(AretError, match="Remplacez d’abord le Front"):
        store.update_brick("TARGET-WASM-01", "DONE", None, None, None, "test")
    with pytest.raises(AretError, match="priority"):
        store.update_brick("TARGET-WASM-02", None, "M8", "wasm32-wasi", 6, "test")

    store.replace_front({"brick": "TARGET-WASM-01", "subsystem": "WASM"}, "test")
    updated = store.update_brick("TARGET-WASM-02", "ACTIVE", "M9", "x64-win11", 1, "test")
    assert updated["state"] == "ACTIVE"
    assert updated["milestone"] == "M9"
    assert updated["target_platform"] == "x64-win11"
    assert updated["priority"] == 1
