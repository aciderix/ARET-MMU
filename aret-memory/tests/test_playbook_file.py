"""Playbook AUTORÉ : la source des lois stables est un fichier Markdown chargé
directement, jamais SQLite. Ces tests verrouillent les trois propriétés qui font le
fix : (1) le playbook vient du fichier ; (2) il est INDÉPENDANT des identifiants
séquentiels de SQLite — un changement de documentation / une re-migration ne peut plus
le casser ni le mésallier ; (3) éditer le playbook ne mute jamais la mémoire SQLite.
"""

from __future__ import annotations

from pathlib import Path

from core.repository import MemoryStore, PLAYBOOK_DOMAINS

_LOREM = " Contenu stable et explicite, suffisamment long pour exercer le plancher de taille du dossier de reprise sans jamais dépendre d'un identifiant SQLite."


def _write_playbook(path: Path, gates_marker: str = "19acad982194bf07") -> None:
    sections = [
        "<!-- fixture playbook autoré -->",
        "# Playbook fixture",
        f"## PLAYBOOK_FOUNDATION — Principe sacré\nCorrect ou arrêt bruyant, jamais de faux silencieux.{_LOREM}",
        f"## PLAYBOOK_METHOD — Méthode\nUne tâche, fixture, vérifier, commit, enregistrer.{_LOREM}",
        f"## PLAYBOOK_ARCHITECTURE — Shared-stack\nesp par valeur, abort sound.{_LOREM}",
        f"## PLAYBOOK_GATES — Portes\nHash {gates_marker} inchangé ; difftest, funcdiff.{_LOREM}",
        f"## PLAYBOOK_TOOLING — Outils\nARET_TRACE, ARET_RELAY, wallsweep.{_LOREM}",
    ]
    path.write_text("\n\n".join(sections) + "\n", encoding="utf-8")


def _ready_store(tmp_path: Path, playbook: Path, monkeypatch) -> MemoryStore:
    monkeypatch.setenv("ARET_PLAYBOOK_PATH", str(playbook))
    store = MemoryStore(tmp_path / "memory", write_enabled=True)
    store.register_component("CORE", "CORE", "fixture", "test")
    store.register_brick("R-1", "Reprise", "ACTIVE", "CORE", "fixture", "test", "M1", "x86-pe32", 1)
    store.update_front({
        "subsystem": "fixture", "brick": "R-1", "current_wall": "test",
        "last_action": "prêt", "next_action": "handoff",
    }, "test")
    store.prepare_handoff(
        work_summary="Vérifier que le playbook autoré est indépendant de SQLite et déterministe pour la reprise.",
        verified_results="Le Front et le handoff sont préparés dans une fixture stricte et reproductible.",
        open_risks="Une dérive silencieuse du playbook serait une faute de type faux-en-silence.",
        deferred_items="Aucun élément n'est présenté comme une capacité non réellement supportée.",
        next_action="Lire le dossier compact puis agir sous portes.",
        technical_checkpoint_state="NONE",
        relevant_addresses=[],
        actor="test",
    )
    return store


def _playbook_map(store: MemoryStore) -> dict[str, str]:
    dossier = store.get_resume_dossier()
    assert dossier["ready"] is True, dossier["errors"]
    return {entry["domains"][0]: entry["content_hash"] for entry in dossier["playbook"]["entries"]}


def test_playbook_comes_from_the_authored_file(tmp_path: Path, monkeypatch) -> None:
    playbook = tmp_path / "playbook.md"
    _write_playbook(playbook)
    store = _ready_store(tmp_path, playbook, monkeypatch)
    dossier = store.get_resume_dossier()
    domains = [entry["domains"][0] for entry in dossier["playbook"]["entries"]]
    assert domains == list(PLAYBOOK_DOMAINS)  # ordre canonique, pas l'ordre du fichier
    text = "\n".join(entry["content"] for entry in dossier["playbook"]["entries"])
    assert "19acad982194bf07" in text
    assert all(entry["address"].startswith("playbook.md#") for entry in dossier["playbook"]["entries"])


def test_playbook_is_independent_of_sqlite_id_churn(tmp_path: Path, monkeypatch) -> None:
    """Le bug historique : le playbook était épinglé à des IDs séquentiels de migration
    et dérivait quand les documents changeaient. Ici on prouve qu'ajouter des masses de
    connaissances (donc décaler toute la numérotation) ne change RIEN au playbook."""
    playbook = tmp_path / "playbook.md"
    _write_playbook(playbook)
    store = _ready_store(tmp_path, playbook, monkeypatch)
    before = _playbook_map(store)

    with store._read_connection() as conn:
        count_before = conn.execute("SELECT COUNT(*) AS n FROM knowledge").fetchone()["n"]
    for index in range(25):
        store.append_knowledge(
            knowledge_type="RULE", status="ACTIVE", title=f"bruit {index}",
            content="Connaissance additionnelle qui décale la numérotation séquentielle des identifiants.",
            component_id="CORE", function_id=None, brick_id=None, tags=[], proof_ids=[],
            supersedes_id=None, actor="test",
        )
    after = _playbook_map(store)
    assert after == before  # playbook strictement inchangé malgré le churn d'IDs

    with store._read_connection() as conn:
        count_after = conn.execute("SELECT COUNT(*) AS n FROM knowledge").fetchone()["n"]
    assert count_after == count_before + 25  # la mémoire vivante a bougé, pas le playbook


def test_editing_the_playbook_file_never_mutates_sqlite(tmp_path: Path, monkeypatch) -> None:
    playbook = tmp_path / "playbook.md"
    _write_playbook(playbook, gates_marker="19acad982194bf07")
    store = _ready_store(tmp_path, playbook, monkeypatch)
    before = _playbook_map(store)
    with store._read_connection() as conn:
        knowledge_before = conn.execute("SELECT COUNT(*) AS n FROM knowledge").fetchone()["n"]
        audit_before = conn.execute("SELECT COUNT(*) AS n FROM audit_event").fetchone()["n"]

    # Éditer le fichier : le contenu GATES change.
    _write_playbook(playbook, gates_marker="DEADBEEFDEADBEEF")
    after = _playbook_map(store)
    assert after["PLAYBOOK_GATES"] != before["PLAYBOOK_GATES"]  # l'édition est reflétée
    assert after["PLAYBOOK_FOUNDATION"] == before["PLAYBOOK_FOUNDATION"]  # le reste stable

    # …mais SQLite n'a pas bougé d'un octet (ni connaissance, ni audit).
    with store._read_connection() as conn:
        knowledge_after = conn.execute("SELECT COUNT(*) AS n FROM knowledge").fetchone()["n"]
        audit_after = conn.execute("SELECT COUNT(*) AS n FROM audit_event").fetchone()["n"]
    assert knowledge_after == knowledge_before
    assert audit_after == audit_before


def test_missing_playbook_is_a_loud_not_ready_dossier(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ARET_PLAYBOOK_PATH", str(tmp_path / "absent.md"))
    store = MemoryStore(tmp_path / "memory", write_enabled=True)
    dossier = store.get_resume_dossier()
    assert dossier["ready"] is False
    assert any("Playbook autoré introuvable" in err for err in dossier["errors"])
