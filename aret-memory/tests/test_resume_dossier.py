from __future__ import annotations

from pathlib import Path

import pytest

from core.repository import AretError, MemoryStore, PLAYBOOK_DOMAINS


PLAYBOOK_PADDING = (
    " Cette règle appartient au contrat stable de reprise : elle s’applique à tout incrément, "
    "doit être explicitement vérifiée avant toute conclusion, et interdit tout résultat supposé. "
    "Les observations, fixtures et preuves doivent rester adressables, déterministes et auditables."
)

PLAYBOOK = (
    ("PLAYBOOK_FOUNDATION", "Principe sound", "Juste ou arrêt bruyant : aucune valeur inventée ni faux succès silencieux."),
    ("PLAYBOOK_METHOD", "Méthode", "Mesurer, reproduire, produire une fixture minimale, implémenter, vérifier puis documenter."),
    ("PLAYBOOK_GATES", "Portes", "cpudiff pour instruction, funcdiff pour lift, winediff pour HLE et hash transpile inchangé pour l’additif."),
    ("PLAYBOOK_TOOLING", "Outils", "ARET_TRACE, WINEDEBUG relay, wallsweep et les pipelines fermés servent à mesurer avant de modifier."),
    ("PLAYBOOK_ARCHITECTURE", "Autonomie", "Wine est une source et un oracle ; le binaire final reste autonome au runtime."),
)


def _store(tmp_path: Path) -> MemoryStore:
    store = MemoryStore(tmp_path / "memory", write_enabled=True)
    store.register_component("CORE", "Noyau", "Fixture Resume Dossier", "test")
    store.register_brick("RESUME-01", "Brique active", "ACTIVE", "CORE", "Fixture", "test", "M1", "x86-pe32", 1)
    for index, (domain, title, content) in enumerate(PLAYBOOK, start=1):
        store.append_knowledge(
            knowledge_type="RULE" if domain != "PLAYBOOK_ARCHITECTURE" else "ARCHITECTURE",
            status="ACTIVE",
            title=title,
            content=content + PLAYBOOK_PADDING,
            component_id="CORE",
            function_id=None,
            brick_id=None,
            tags=["CORE_PLAYBOOK", domain, *( ["PLAYBOOK_SHARED_STACK"] if domain == "PLAYBOOK_ARCHITECTURE" else [] )],
            proof_ids=[],
            supersedes_id=None,
            actor="test",
        )
    hot = store.append_knowledge(
        knowledge_type="STATE",
        status="ACTIVE",
        title="Contexte chaud",
        content="La brique de reprise est prête pour une action atomique.",
        component_id="CORE",
        function_id=None,
        brick_id="RESUME-01",
        tags=["HOT"],
        proof_ids=[],
        supersedes_id=None,
        actor="test",
    )
    store.update_front({
        "subsystem": "Fixture",
        "brick": "RESUME-01",
        "current_wall": "Validation du Resume Dossier",
        "last_action": "Playbook tagué initialisé.",
        "next_action": "Préparer le handoff actif complet avant de démarrer la reprise.",
        "relevant_1_address": hot["address"],
    }, "test")
    return store


def _handoff(store: MemoryStore) -> dict[str, object]:
    return store.prepare_handoff(
        work_summary="Le playbook stable est sélectionné et le mécanisme de reprise est prêt à être validé.",
        verified_results="Les tests unitaires de la mémoire sont verts et le contrôle MCP est prêt à être exécuté.",
        open_risks="Aucun risque bloquant connu ; toute divergence doit produire un arrêt bruyant.",
        deferred_items="Aucun élément différé ne doit être traité avant la validation de la reprise active.",
        next_action="Exécuter le contrôle MCP puis confirmer le rituel de reprise avec le dossier injecté.",
        relevant_addresses=[],
        actor="test",
    )


def test_resume_dossier_requires_all_playbook_domains_and_handoff(tmp_path: Path) -> None:
    store = _store(tmp_path)

    before = store.get_resume_dossier()
    assert before["ready"] is False
    assert "handoff" in before["errors"][0].lower()

    updated = _handoff(store)
    assert updated["ready"] is True

    dossier = store.get_resume_dossier()
    assert dossier["ready"] is True
    assert dossier["playbook"]["domains"] == list(PLAYBOOK_DOMAINS)
    assert len(dossier["playbook"]["entries"]) == len(PLAYBOOK)
    assert dossier["handoff"]["next_action"].startswith("Exécuter le contrôle MCP")
    assert dossier["contract_hash"]


def test_prepare_handoff_is_atomic_and_rejects_unaddressed_hot_context(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(AretError, match="adresse ARET"):
        store.prepare_handoff(
            work_summary="Résumé suffisamment détaillé de l’état de travail courant.",
            verified_results="Résultats vérifiés et explicitement décrits.",
            open_risks="Risques ouverts explicitement décrits.",
            deferred_items="Éléments différés explicitement décrits.",
            next_action="Poursuivre avec une action atomique et vérifiable.",
            relevant_addresses=["pas-une-adresse"],
            actor="test",
        )
    assert "handoff_work_summary" not in store.get_front()["state"]


def test_resume_dossier_turns_stale_after_a_front_change(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _handoff(store)
    assert store.get_resume_dossier()["ready"] is True

    store.update_front({"current_wall": "Un nouveau mur rend le handoff précédent périmé."}, "test")
    stale = store.get_resume_dossier()
    assert stale["ready"] is False
    assert any("périmé" in error for error in stale["errors"])
