from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

import core.repository as repository
from core.repository import AretError, MemoryStore, NotFoundError, WriteDisabledError
from evidence.capture import create_receipt


def make_store(tmp_path: Path, *, write_enabled: bool = True) -> MemoryStore:
    return MemoryStore(tmp_path / ".aret-memory", write_enabled=write_enabled, proof_hmac_secret="test-secret")


def signed_pass_receipt() -> str:
    payload = {
        "kind": "DIFFTEST",
        "command": "difftest --case eh-03",
        "result": "PASS",
        "exit_code": 0,
        "artifact_path": "",
        "artifact_hash": "",
        "environment": {"oracle": "difftest", "version": "1"},
        "started_at": "2026-08-19T10:00:00Z",
        "finished_at": "2026-08-19T10:00:01Z",
    }
    return create_receipt(payload, "test-secret")["receipt_hmac"]


def record_admissible_proof(store: MemoryStore) -> str:
    proof = store.record_proof(
        kind="DIFFTEST",
        command="difftest --case eh-03",
        result="PASS",
        exit_code=0,
        stdout_ref="",
        stderr_ref="",
        artifact_path="",
        artifact_hash="",
        environment={"oracle": "difftest", "version": "1"},
        started_at="2026-08-19T10:00:00Z",
        finished_at="2026-08-19T10:00:01Z",
        receipt_hmac=signed_pass_receipt(),
        actor="difftest-adapter",
    )
    assert proof["admissible"] == 1
    return proof["id"]


def test_reopening_existing_store_in_read_mode_preserves_metadata(tmp_path: Path, monkeypatch) -> None:
    memory_dir = tmp_path / ".aret-memory"
    MemoryStore(memory_dir, write_enabled=True)
    with sqlite3.connect(memory_dir / "aret_memory.sqlite") as connection:
        before = connection.execute(
            "SELECT key, value, updated_at FROM store_metadata ORDER BY key"
        ).fetchall()

    monkeypatch.setattr(repository, "utc_now", lambda: "2099-01-01T00:00:00Z")
    MemoryStore(memory_dir, write_enabled=False)
    with sqlite3.connect(memory_dir / "aret_memory.sqlite") as connection:
        after = connection.execute(
            "SELECT key, value, updated_at FROM store_metadata ORDER BY key"
        ).fetchall()

    assert after == before


def test_boot_and_readonly_guard(tmp_path: Path) -> None:
    store = make_store(tmp_path, write_enabled=False)
    boot = store.boot()
    assert boot["write_enabled"] is False
    assert "SQLite est la source canonique" in boot["doctrine"]
    with pytest.raises(WriteDisabledError):
        store.register_component("EH", "Exception handling", "", "test")


def test_proven_requires_trusted_pass_proof(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.register_component("EH", "Exception handling", "", "test")
    with pytest.raises(AretError, match="PROVEN exige"):
        store.append_knowledge(
            knowledge_type="FORENSIC", status="PROVEN", title="Dérive ESP", content="Contenu exact",
            component_id="EH", function_id=None, brick_id=None, tags=["EH", "ABI"], proof_ids=[], supersedes_id=None, actor="test",
        )
    proof_id = record_admissible_proof(store)
    knowledge = store.append_knowledge(
        knowledge_type="FORENSIC", status="PROVEN", title="Dérive ESP", content="Contenu exact",
        component_id="EH", function_id=None, brick_id=None, tags=["EH", "ABI"], proof_ids=[proof_id], supersedes_id=None, actor="test",
    )
    assert knowledge["status"] == "PROVEN"
    assert knowledge["proof_ids"] == [proof_id]
    proofs = store.get_proofs(knowledge["id"])
    assert proofs["proofs"][0]["result"] == "PASS"
    assert proofs["proofs"][0]["admissible"] == 1


def test_find_then_exact_read_and_bounded_batch(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.register_component("EH", "Exception handling", "", "test")
    item = store.append_knowledge(
        knowledge_type="OBSERVATION", status="OBSERVED", title="Callee pop observé",
        content="La trace confirme un callee-pop sur la fonction cible.", component_id="EH",
        function_id=None, brick_id=None, tags=["EH", "ABI"], proof_ids=[], supersedes_id=None, actor="test",
    )
    found = store.find(component_id="EH", tag="ABI", text="callee pop")
    assert len(found["items"]) == 1
    assert "content" not in found["items"][0]
    assert found["items"][0]["address"] == item["address"]
    exact = store.read(item["address"])
    assert exact["content"] == "La trace confirme un callee-pop sur la fonction cible."
    batch = store.read_batch([item["address"]], max_items=1, max_bytes=4096)
    assert batch["items"][0]["content_hash"] == exact["content_hash"]
    with pytest.raises(AretError, match="dépasse max_bytes"):
        store.read_batch([item["address"]], max_items=1, max_bytes=10)
    with pytest.raises(NotFoundError):
        store.read("ARET://knowledge/EH-9999")


def test_append_versioning_audit_and_rebuild(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.register_component("EH", "Exception handling", "", "test")
    original = store.append_knowledge(
        knowledge_type="HYPOTHESIS", status="HYPOTHESIS", title="Hypothèse A", content="Piste initiale.",
        component_id="EH", function_id=None, brick_id=None, tags=["EH"], proof_ids=[], supersedes_id=None, actor="test",
    )
    successor = store.append_knowledge(
        knowledge_type="OBSERVATION", status="OBSERVED", title="Observation A", content="Validation mesurée.",
        component_id="EH", function_id=None, brick_id=None, tags=["EH"], proof_ids=[], supersedes_id=original["id"], actor="test",
    )
    previous = store.read(original["address"])
    assert previous["status"] == "SUPERSEDED"
    relations = store.get_related(successor["id"], relation_type="SUPERSEDES", direction="outgoing")
    assert relations["relations"][0]["to_id"] == original["id"]
    with store._connection() as conn:  # Simule la perte de cache dérivé, jamais de données canoniques.
        conn.execute("DELETE FROM knowledge_fts")
        conn.commit()
    rebuilt = store.rebuild_index("test")
    assert rebuilt["indexed_items"] == 2
    found = store.find(text="Validation mesurée")
    assert found["items"][0]["address"] == successor["address"]
    events = store.audit_events()
    assert any(event["operation"] == "APPEND_KNOWLEDGE" for event in events)
    assert any(event["operation"] == "REBUILD_FTS" for event in events)


def test_artifact_integrity_and_explicit_bounded_read(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    artifact = store.artifacts_dir / "proof.log"
    artifact.write_text("ligne 1\nligne 2\n", encoding="utf-8")
    artifact_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
    payload = {
        "kind": "WINEDIFF", "command": "winediff --case 1", "result": "PASS", "exit_code": 0,
        "artifact_path": "proof.log", "artifact_hash": artifact_hash, "environment": {"oracle": "winediff"},
        "started_at": None, "finished_at": None,
    }
    receipt = create_receipt(payload, "test-secret")["receipt_hmac"]
    proof = store.record_proof(
        kind="WINEDIFF", command="winediff --case 1", result="PASS", exit_code=0, stdout_ref="", stderr_ref="",
        artifact_path="proof.log", artifact_hash=artifact_hash, environment={"oracle": "winediff"},
        started_at=None, finished_at=None, receipt_hmac=receipt, actor="winediff-adapter",
    )
    content = store.read_artifact(proof["id"], max_bytes=7)
    assert content["truncated"] is True
    assert content["content"] == "ligne 1"
    artifact.write_text("altéré", encoding="utf-8")
    with pytest.raises(AretError, match="Intégrité"):
        store.read_artifact(proof["id"])
