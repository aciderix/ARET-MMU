from __future__ import annotations

from pathlib import Path

import pytest

from core.repository import AretError, MemoryStore
from evidence.adapters import oracles
from evidence.adapters.oracles import OracleSpec, run_oracle


def prepared_store(memory_dir: Path, secret: str = "test-secret") -> tuple[MemoryStore, str]:
    store = MemoryStore(memory_dir, write_enabled=True, proof_hmac_secret=secret)
    store.register_component("CORE", "Noyau", "Test", "test")
    knowledge = store.append_knowledge(
        knowledge_type="OBSERVATION", status="OBSERVED", title="Hypothèse mesurée", content="À valider par oracle.",
        component_id="CORE", function_id=None, brick_id=None, tags=["TEST"], proof_ids=[], supersedes_id=None, actor="test",
    )
    return store, knowledge["id"]


def oracle_repository(tmp_path: Path, script_text: str) -> Path:
    repository = tmp_path / "repository"
    script = repository / "bench" / "difftest.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/usr/bin/env bash\nset -u\n" + script_text + "\n", encoding="utf-8")
    script.chmod(0o755)
    binary = repository / "target" / "release" / "aret"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)
    return repository


def test_oracle_pass_creates_signed_proof_links_and_promotes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repository = oracle_repository(tmp_path, "echo 'differential equivalence: 1/1 functions'")
    monkeypatch.setitem(oracles.ORACLES, "difftest", OracleSpec("difftest", "DIFFTEST", "bench/difftest.sh", ("bash",), 20))
    store, knowledge_id = prepared_store(tmp_path / "memory")

    result = run_oracle(store, repository, "difftest", knowledge_id, promote=True)
    proof = result["proof"]
    assert result["execution"]["result"] == "PASS"
    assert proof["admissible"] == 1
    assert result["attachment"]["promoted"] is True
    assert store.read(f"ARET://knowledge/{knowledge_id}")["status"] == "PROVEN"
    assert (store.artifacts_dir / result["artifact"]["path"]).is_file()


def test_oracle_fail_is_recorded_without_promotion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repository = oracle_repository(tmp_path, "echo 'mismatch: orig=1 aret=2'; exit 1")
    monkeypatch.setitem(oracles.ORACLES, "difftest", OracleSpec("difftest", "DIFFTEST", "bench/difftest.sh", ("bash",), 20))
    store, knowledge_id = prepared_store(tmp_path / "memory")

    result = run_oracle(store, repository, "difftest", knowledge_id, promote=False)
    assert result["execution"]["result"] == "FAIL"
    assert result["proof"]["result"] == "FAIL"
    assert store.read(f"ARET://knowledge/{knowledge_id}")["status"] == "OBSERVED"


def test_missing_oracle_dependency_is_explicit_skip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repository = oracle_repository(tmp_path, "echo should-not-run; exit 1")
    monkeypatch.setitem(oracles.ORACLES, "difftest", OracleSpec("difftest", "DIFFTEST", "bench/difftest.sh", ("definitely-missing-aret-tool",), 20))
    store, _ = prepared_store(tmp_path / "memory")

    result = run_oracle(store, repository, "difftest")
    assert result["execution"]["result"] == "SKIPPED"
    assert result["proof"]["result"] == "SKIPPED"
    assert result["execution"]["missing_dependencies"] == ["definitely-missing-aret-tool"]


def test_attach_nonadmissible_pass_cannot_promote(tmp_path: Path) -> None:
    store, knowledge_id = prepared_store(tmp_path / "memory")
    proof = store.record_proof(
        kind="DIFFTEST", command="test", result="PASS", exit_code=0, stdout_ref="", stderr_ref="",
        artifact_path="", artifact_hash="", environment={}, started_at=None, finished_at=None, receipt_hmac="", actor="test",
    )
    with pytest.raises(AretError, match="PASS et admissible"):
        store.attach_proof(knowledge_id, proof["id"], "test", promote=True)
    assert store.read(f"ARET://knowledge/{knowledge_id}")["status"] == "OBSERVED"
