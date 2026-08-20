from __future__ import annotations

from pathlib import Path

import pytest

from core.repository import AretError, MemoryStore
from evidence.adapters import pipelines
from evidence.adapters.pipelines import PipelineSpec, pipeline_catalog, register_asset, run_pipeline


def fake_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    script = repository / "bench" / "regression.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/usr/bin/env bash\necho 'regression gate: PASS'\n", encoding="utf-8")
    script.chmod(0o755)
    return repository


def test_catalog_exposes_closed_policies() -> None:
    catalog = pipeline_catalog()
    assert catalog["network_confirmation_required"] is True
    assert catalog["sensitive_confirmation_required"] is True
    assert any(item["name"] == "measure_binary_walls" for item in catalog["policies"]["READ_ONLY"])
    assert any(item["name"] == "fetch_wall_corpus" for item in catalog["policies"]["NETWORK"])


def test_pipeline_dry_run_is_default_safe_plan(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory", write_enabled=True)
    repository = fake_repository(tmp_path)
    result = run_pipeline(store, repository, "generate_stdcall_pops")
    assert result["dry_run"] is True
    assert result["confirmation_required"]["confirm_apply"] is True
    assert store.get_pipeline_runs()["runs"] == []


def test_network_and_sensitive_pipelines_require_explicit_confirmation(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory", write_enabled=True)
    repository = fake_repository(tmp_path)
    assert run_pipeline(store, repository, "fetch_wall_corpus")["dry_run"] is True
    assert run_pipeline(store, repository, "capture_snapshot", {"pid": 123})["dry_run"] is True
    with pytest.raises(AretError, match="confirm_network"):
        run_pipeline(store, repository, "fetch_wall_corpus", dry_run=False)
    with pytest.raises(AretError, match="confirm_sensitive"):
        run_pipeline(store, repository, "capture_snapshot", dry_run=False)


def test_closed_pipeline_persists_hashable_run_and_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = MemoryStore(tmp_path / "memory", write_enabled=True)
    repository = fake_repository(tmp_path)
    monkeypatch.setitem(
        pipelines.PIPELINES,
        "test_pipeline",
        PipelineSpec("test_pipeline", "TEST_PIPELINE", "READ_ONLY", "Test fermé", ("bash",), 30, "regression"),
    )
    result = run_pipeline(store, repository, "test_pipeline", dry_run=False)
    assert result["execution"]["result"] == "PASS"
    pipeline_id = result["run"]["id"]
    assert result["run"]["address"] == f"ARET://pipeline/{pipeline_id}"
    listed = store.get_pipeline_runs("test_pipeline")
    assert listed["runs"][0]["id"] == pipeline_id
    artifact = store.read_pipeline_artifact(pipeline_id)
    assert "regression gate: PASS" in artifact["content"]


def test_asset_import_requires_consent_and_is_addressable(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory", write_enabled=True)
    repository = fake_repository(tmp_path)
    asset = repository / "fixture.exe"
    asset.write_bytes(b"MZtest-asset")
    with pytest.raises(AretError, match="confirm_import"):
        register_asset(store, repository, "fixture.exe", "PE32", confirm_import=False)
    imported = register_asset(store, repository, "fixture.exe", "PE32", confirm_import=True)
    assert imported["address"].startswith("ARET://asset/AS-")
    assert imported["sha256"]
    assert (store.artifacts_dir / imported["relative_path"]).is_file()


def test_resume_brief_returns_addressable_rules_journal_and_audit(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory", write_enabled=True)
    store.register_component("CORE", "Noyau", "Test", "test")
    store.append_knowledge(
        knowledge_type="RULE", status="ACTIVE", title="Règle durable", content="Correct ou abort.",
        component_id="CORE", function_id=None, brick_id=None, tags=["RULE"], proof_ids=[], supersedes_id=None,
        actor="test", document_source={
            "repository": "aciderix/ARET", "revision": "abc123", "path": "docs/vision/70-reference-etat-methode-reste.md",
            "start_line": 1, "end_line": 2, "section": "§0", "hash": "a" * 64,
        },
    )
    store.append_knowledge(
        knowledge_type="MEASUREMENT", status="OBSERVED", title="Journal récent", content="Mesure.",
        component_id="CORE", function_id=None, brick_id=None, tags=["JOURNAL"], proof_ids=[], supersedes_id=None,
        actor="test", document_source={
            "repository": "aciderix/ARET", "revision": "abc123", "path": "docs/vision/71-journal-de-bord.md",
            "start_line": 99, "end_line": 100, "section": "Entrée", "hash": "b" * 64,
        },
    )
    brief = store.get_resume_brief()
    assert brief["rules"][0]["address"].startswith("ARET://knowledge/")
    assert brief["latest_document_71_entries"][0]["title"] == "Journal récent"
    assert brief["recent_audit"]
