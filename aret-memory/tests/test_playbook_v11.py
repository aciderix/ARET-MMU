from __future__ import annotations

from pathlib import Path

from core.repository import MemoryStore
from migration.bootstrap_playbook_v11 import SPECS, apply

PADDING = (
    " Cette source est une fixture canonique de migration ; son contenu reste suffisamment explicite, stable, "
    "audit-able et long pour exercer le plancher de taille du Resume Dossier."
)


def _append(store: MemoryStore, component_id: str, knowledge_type: str, title: str, content: str) -> None:
    store.append_knowledge(
        knowledge_type=knowledge_type,
        status="ACTIVE",
        title=title,
        content=content + PADDING,
        component_id=component_id,
        function_id=None,
        brick_id=None,
        tags=[],
        proof_ids=[],
        supersedes_id=None,
        actor="test",
    )


def _source_store(tmp_path: Path) -> MemoryStore:
    store = MemoryStore(tmp_path / "memory", write_enabled=True)
    for component_id in ("CORE", "ARCH", "INDUS", "CORPUS", "FIBER", "INFRA"):
        store.register_component(component_id, component_id, "Fixture V1.1", "test")
    store.register_brick("RESUME-11", "Reprise V1.1", "ACTIVE", "CORE", "Fixture", "test", "M1", "x86-pe32", 1)

    for index in range(1, 8):
        title = {
            1: "Principe sound",
            5: "Réutilisation vérifiée",
            6: "Méthode de travail",
            7: "Deux pipelines et hash d’or 19acad982194bf07",
        }.get(index, f"Source CORE {index}")
        _append(store, "CORE", "RULE", title, f"Source CORE {index} : reproduire, fixture, vérifier et cpudiff.")
    for index in range(1, 10):
        _append(store, "ARCH", "ARCHITECTURE", f"Source ARCH {index}", "Architecture shared-stack et abort sound.")
    for index in range(1, 14):
        _append(store, "INDUS", "RULE", f"Source INDUS {index}", "Portes et industrialisation déterministes.")
    for index in range(1, 54):
        title = "Outil relay ARET_RELAY=1 WINEDEBUG=+relay" if index == 53 else f"Source INDUS {index + 13}"
        _append(store, "INDUS", "RULE", title, "Diff relay et première divergence API.")
    for index in range(1, 7):
        _append(store, "CORPUS", "RULE", f"Source CORPUS {index}", "Wallsweep et mesure de corpus.")
    _append(store, "FIBER", "ARCHITECTURE", "Source Fiber", "Contexte shared-stack.")
    for index in range(1, 18):
        title = "Outil ARET_TRACE=1" if index == 3 else "Outil ARET_DEBUG=1 -g" if index == 17 else f"Source INFRA {index}"
        _append(store, "INFRA", "RULE", title, "Diagnostic déterministe et preuve admissible.")

    store.update_front({
        "subsystem": "Fixture V1.1", "brick": "RESUME-11", "current_wall": "Validation du playbook dérivé",
        "last_action": "Sources de migration préparées.", "next_action": "Préparer le handoff V1.1.",
    }, "test")
    return store


def _handoff(store: MemoryStore) -> None:
    store.prepare_handoff(
        work_summary="Le playbook V1.1 dérivé est préparé dans une fixture SQLite strictement déterministe.",
        verified_results="Les sources et relations de provenance sont disponibles, hashées et testées.",
        open_risks="Une divergence du Front doit toujours rendre le handoff et le dossier périmés.",
        deferred_items="Aucun élément différé ne peut être présenté comme une capacité effectivement supportée.",
        next_action="Lire le dossier compact puis choisir une action atomique gardée par ses portes.",
        relevant_addresses=[],
        actor="test",
    )


def test_playbook_v11_bootstrap_is_idempotent_and_injects_operational_rules(tmp_path: Path) -> None:
    store = _source_store(tmp_path)
    first = apply(store, actor="test-v11")

    assert first["counts"] == {"created": 3, "existing": 0, "relations_created": 6, "relations_existing": 0}
    _handoff(store)
    dossier = store.get_resume_dossier()
    text = "\n".join(entry["content"] for entry in dossier["playbook"]["entries"])
    assert dossier["ready"] is True
    assert dossier["size_bytes"] <= dossier["max_bytes"]
    for expected in ("Borner puis pivoter", "19acad982194bf07", "cpudiff + funcdiff", "ARET_TRACE=1", "ARET_RELAY=1", "ARET_DEBUG=1", "wallsweep.sh"):
        assert expected in text

    second = apply(store, actor="test-v11")
    assert second["counts"] == {"created": 0, "existing": 3, "relations_created": 0, "relations_existing": 6}


def test_prepare_handoff_never_bootstraps_playbook(tmp_path: Path) -> None:
    store = _source_store(tmp_path)
    apply(store, actor="test-v11")

    def forbidden(_: str) -> dict[str, object]:
        raise AssertionError("Le bootstrap ne doit jamais être appelé par prepare_handoff")

    store._bootstrap_resume_playbook = forbidden  # type: ignore[method-assign]
    _handoff(store)
    assert store.get_resume_dossier()["ready"] is True
    assert len(SPECS) == 3
