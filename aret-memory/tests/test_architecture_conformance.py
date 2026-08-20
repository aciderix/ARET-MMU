from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from core.repository import MemoryStore
from evidence.capture import create_receipt
from hooks.common import additional_context


def signed_proof(store: MemoryStore) -> dict[str, object]:
    payload = {
        "kind": "DIFFTEST", "command": "bench/difftest.sh", "result": "PASS", "exit_code": 0,
        "artifact_path": "", "artifact_hash": "", "environment": {"test": True},
        "started_at": "2026-08-19T00:00:00Z", "finished_at": "2026-08-19T00:00:01Z",
    }
    receipt = create_receipt(payload, "audit-secret")
    return store.record_proof(**payload, stdout_ref="", stderr_ref="", receipt_hmac=receipt["receipt_hmac"], actor="test")


def _ready_dossier(front: dict[str, object]) -> dict[str, object]:
    return {
        "ready": True,
        "contract_hash": "fixture-contract",
        "prepared_at": "2026-08-20T00:00:00Z",
        "playbook": {"entries": [{
            "title": "Règle fixture", "domains": ["PLAYBOOK_FOUNDATION"],
            "address": "ARET://knowledge/CORE-0001", "content": "Juste ou arrêt bruyant.",
        }]},
        "handoff": {
            "handoff_work_summary": "Fixture de contexte prête.",
            "handoff_verified_results": "Les tests de fixture sont disponibles.",
            "handoff_open_risks": "Aucun risque de fixture.",
            "handoff_deferred_items": "Aucun différé de fixture.",
            "next_action": "Vérifier l’enveloppe du hook.",
        },
        "front": front,
    }


def populated_store(tmp_path: Path) -> tuple[MemoryStore, str]:
    store = MemoryStore(tmp_path / "memory", write_enabled=True, proof_hmac_secret="audit-secret")
    store.register_component("CORE", "Core <unsafe>", "Test", "test")
    knowledge = store.append_knowledge(
        knowledge_type="OBSERVATION", status="OBSERVED", title="Titre <script>", content="Contenu <b>brut</b>",
        component_id="CORE", function_id=None, brick_id=None, tags=["TEST"], proof_ids=[], supersedes_id=None, actor="test",
    )
    return store, knowledge["id"]


def test_invalidate_proof_demotes_unjustified_proven(tmp_path: Path) -> None:
    store, knowledge_id = populated_store(tmp_path)
    proof = signed_proof(store)
    store.attach_proof(knowledge_id, proof["id"], "test", promote=True)
    result = store.invalidate_proof(proof["id"], "Oracle retiré", "auditor")
    assert result["demoted_knowledge_ids"] == [knowledge_id]
    assert store.read(f"ARET://knowledge/{knowledge_id}")["status"] == "OBSERVED"
    assert store.read(f"ARET://proof/{proof['id']}")["admissible"] == 0
    assert any(event["operation"] == "INVALIDATE_PROOF" for event in store.audit_events())


def test_restore_and_rebuild_front_are_compact_and_deterministic(tmp_path: Path) -> None:
    store, knowledge_id = populated_store(tmp_path)
    restored = store.restore()
    assert restored["front_address"] == "ARET://front/current"
    rebuilt = store.rebuild_front("test")
    assert f"ARET://knowledge/{knowledge_id}" in rebuilt["derived_addresses"]
    context = additional_context({**restored, "front": rebuilt["front"], "resume_dossier": _ready_dossier(rebuilt["front"])})
    assert "ARET-MMU" in context
    assert len(context) < 10_000


def test_html_export_is_derived_and_escaped(tmp_path: Path) -> None:
    store, _ = populated_store(tmp_path)
    output = store.export("html", "audit-html")
    page = Path(output["path"]).read_text(encoding="utf-8")
    assert output["format"] == "html"
    assert "Titre &lt;script&gt;" in page
    assert "Contenu &lt;b&gt;brut&lt;/b&gt;" in page
    assert "SQLite reste la source canonique" in page


def test_bundle_v3_contains_hashed_migrations(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ARET_SOURCE_DEVICE_ID", "device-a")
    store, _ = populated_store(tmp_path)
    bundle = store.export_bundle("audit-bundle")
    with zipfile.ZipFile(bundle["path"]) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["bundle_version"] == 3
        assert manifest["source_device_id"] == "device-a"
        assert manifest["migrations"]
        for item in manifest["migrations"]:
            data = archive.read(f"schema/{item['name']}")
            assert hashlib.sha256(data).hexdigest() == item["sha256"]


def test_compaction_checkpoints_are_audited_without_creating_knowledge(tmp_path: Path) -> None:
    store, _ = populated_store(tmp_path)
    pre = store.record_session_checkpoint("PRE_COMPACT", "session-a", "auto", None, "hook")
    post = store.record_session_checkpoint("POST_COMPACT", "session-a", "auto", "Résumé borné", "hook")
    assert pre["event"] == "PRE_COMPACT"
    assert post["event"] == "POST_COMPACT"
    events = [event for event in store.audit_events() if event["operation"] == "SESSION_CHECKPOINT"]
    assert len(events) == 2
    assert "Résumé borné" in events[0]["payload_after"]


def test_sessionstart_context_uses_official_hook_envelope(tmp_path: Path) -> None:
    front = {"state": {"subsystem": {"value": "EH"}}, "relevant_addresses": ["ARET://knowledge/EH-0001"]}
    restored = {
        "doctrine": "SQLite canonique.", "memory_format_version": "3", "policy_version": "1",
        "front": front, "resume_dossier": _ready_dossier(front),
    }
    context = additional_context(restored)
    envelope = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
    assert envelope["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "ARET://knowledge/EH-0001" in envelope["hookSpecificOutput"]["additionalContext"]
