from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
from pre_compact import handler as precompact_handler
from core.repository import AretError, MemoryStore, utc_now
from test_resume_dossier import _store


def _record_pipeline(store: MemoryStore, name: str, result: str = "PASS", parameters: dict[str, object] | None = None) -> dict[str, object]:
    relative = f"v13/{name}_{result}_{utc_now().replace(':', '')}.json"
    path = store.artifacts_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format": "aret-pipeline-artifact/v1",
        "pipeline": name,
        "result": result,
        "parameters": parameters or {},
    }
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return store.record_pipeline_run(
        pipeline_name=name,
        kind="V13_TEST",
        policy="READ_ONLY",
        result=result,
        command=f"closed:{name}",
        parameters=parameters or {},
        artifact_path=relative,
        artifact_hash=digest,
        exit_code=0 if result == "PASS" else 1,
        started_at=utc_now(),
        finished_at=utc_now(),
        actor="v13-test",
    )


def _active_handoff(store: MemoryStore, last_validation: str) -> dict[str, object]:
    return store.prepare_handoff(
        work_summary="Le geste V1.3 est préparé afin de distinguer explicitement une déclaration technique des faits MCP observables.",
        verified_results="Les résultats de pipeline restent des faits adressables ; aucun verdict non observé ne doit être présenté comme prouvé.",
        open_risks="Une compaction peut intervenir après une opération MCP sans que le checkpoint déclaratif soit mis à jour.",
        deferred_items="Toute interprétation de l’intention de l’agent reste interdite et demeure hors de la couche d’observations.",
        next_action="Lire les observations factuelles puis poursuivre uniquement avec les actions déclarées dans le checkpoint actif.",
        technical_checkpoint_state="ACTIVE",
        technical_target="aret-memory/hooks/common.py — rendu des observations V1.3",
        technical_change="Le bloc factuel est séparé du checkpoint déclaratif sans modifier ses cinq champs.",
        execution_state="Aucun processus en cours ; le prochain pipeline produira un fait machine séparé.",
        last_validation=last_validation,
        immediate_actions="Lancer le pipeline fermé, lire son fait observé, puis acquitter le dossier contractuel.",
        relevant_addresses=[],
        actor="v13-test",
    )


def test_observations_start_after_atomic_handoff_cutoff_and_change_only_contract_hash(tmp_path: Path) -> None:
    store = _store(tmp_path)
    reference = _record_pipeline(store, "run_magicdiv_check", "PASS", {"fixture": "before"})
    prepared = _active_handoff(store, f"run_magicdiv_check PASS {reference['address']}")
    assert prepared["observations"]["total"] == 0
    front_hash = prepared["front"]["state"]["handoff_front_hash"]["value"]
    contract_before = prepared["contract_hash"]

    created = [
        _record_pipeline(store, "run_magicdiv_check", "PASS", {"fixture": str(index), "mode": "strict"})
        for index in range(4)
    ]
    dossier = store.get_resume_dossier()
    observations = dossier["observations"]
    assert dossier["ready"] is True
    assert observations["total"] == 4
    assert len(observations["items"]) == 3
    assert observations["items"][0]["address"] == created[-1]["address"]
    assert observations["items"][0]["parameters"] == "fixture=3, mode=strict"
    assert dossier["front"]["state"]["handoff_front_hash"]["value"] == front_hash
    assert dossier["contract_hash"] != contract_before


def test_machine_reference_is_verified_or_contradiction_is_refused(tmp_path: Path) -> None:
    store = _store(tmp_path)
    failed = _record_pipeline(store, "run_magicdiv_check", "FAIL")
    with pytest.raises(AretError, match="contradictoire"):
        _active_handoff(store, f"run_magicdiv_check PASS {failed['address']}")
    assert "handoff_work_summary" not in store.get_front()["state"]

    declared = _active_handoff(store, "funcdiff PASS observé hors MCP, sans adresse de pipeline ni de preuve.")
    status = declared["handoff"]["technical_checkpoint"]["last_validation_machine_status"]
    assert status["status"] == "DECLARED_UNVERIFIED"


def test_precompact_returns_only_factual_observations_without_creating_intention(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _active_handoff(store, "Aucun verdict machine nouveau n’est déclaré.")
    run = _record_pipeline(store, "run_magicdiv_check", "SKIPPED", {"reason": "dependency"})
    payload = precompact_handler(store, {"session_id": "v13", "audit_limit": 4})
    observations = payload["observations"]
    assert observations["total"] == 1
    assert observations["items"][0]["address"] == run["address"]
    assert observations["items"][0]["result"] == "SKIPPED"
    assert "checkpoint technique" not in payload["notice"].lower()
    assert store.get_front()["state"]["handoff_technical_target"]["value"] == "aret-memory/hooks/common.py — rendu des observations V1.3"
