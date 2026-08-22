"""Doctor de cohérence interne (DB-primaire).

`health_report()` est la porte PERMANENTE de robustesse : elle vérifie que la mémoire
vivante est saine EN ELLE-MÊME, indépendamment des documents et de toute révision Git.
Ces tests verrouillent un cas sain et trois modes de panne réels.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.repository import MemoryStore


def _store(tmp_path: Path) -> MemoryStore:
    store = MemoryStore(tmp_path / "memory", write_enabled=True)
    store.register_component("CORE", "Noyau", "test", "test")
    store.append_knowledge(
        knowledge_type="OBSERVATION", status="OBSERVED", title="Objet", content="Contenu.",
        component_id="CORE", function_id=None, brick_id=None, tags=[], proof_ids=[], supersedes_id=None, actor="test",
    )
    store.update_front({"subsystem": "test", "current_wall": "x", "last_action": "y", "next_action": "z"}, "test")
    return store


def _check(report: dict, name: str) -> bool:
    return next(c["ok"] for c in report["checks"] if c["check"] == name)


def test_healthy_memory_passes_doctor(tmp_path: Path) -> None:
    report = _store(tmp_path).health_report()
    assert report["ok"] is True, report["errors"]
    assert _check(report, "playbook_cinq_domaines") is True     # depuis le fichier empaqueté
    assert _check(report, "proven_requiert_preuve_admissible") is True
    assert _check(report, "fts_reconstructible") is True
    assert _check(report, "relations_sans_orphelin") is True


def test_doctor_flags_missing_playbook(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ARET_PLAYBOOK_PATH", str(tmp_path / "absent.md"))
    report = _store(tmp_path).health_report()
    assert report["ok"] is False
    assert _check(report, "playbook_cinq_domaines") is False


def test_doctor_flags_stale_handoff(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.prepare_handoff(
        work_summary="Handoff préparé pour vérifier la détection d'un Front qui change ensuite.",
        verified_results="Les objets de test sont enregistrés dans la mémoire canonique.",
        open_risks="Un handoff périmé doit être détecté par le doctor de cohérence.",
        deferred_items="Aucun élément différé dans cette fixture.",
        next_action="Modifier le Front puis exécuter le doctor.",
        technical_checkpoint_state="NONE", relevant_addresses=[], actor="test",
    )
    assert _check(store.health_report(), "handoff_frais") is True
    # Le Front change APRÈS la préparation ⇒ handoff périmé.
    store.update_front({"current_wall": "un mur différent"}, "test")
    report = store.health_report()
    assert _check(report, "handoff_frais") is False
    assert report["ok"] is False


def test_doctor_flags_orphan_relation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    # Corruption simulée (hors API) : une relation pointant une entité inexistante.
    conn = sqlite3.connect(store.db_path)
    conn.execute(
        "INSERT INTO relation(id, from_id, relation_type, to_id, created_at, created_by) VALUES (?,?,?,?,?,?)",
        ("REL-ORPHAN", "CORE", "CONCERNS", "KNOWLEDGE-INEXISTANT", "2026-01-01T00:00:00Z", "corruption"),
    )
    conn.commit()
    conn.close()
    report = store.health_report()
    assert _check(report, "relations_sans_orphelin") is False
    assert report["ok"] is False
