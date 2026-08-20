#!/usr/bin/env python3
"""Bootstrap idempotent du Playbook opérationnel Resume Dossier V1.1.

Ce script est une migration explicite à exécuter une fois par Store. Il complète
le noyau V1 par trois fiches dérivées, compactes et directement injectables :
méthode, portes de validation et outillage de diagnostic. Il ne fait partie ni
du chemin du handoff ni d'un hook de session.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.repository import (  # noqa: E402
    AretError,
    CORE_PLAYBOOK_TAG,
    MemoryStore,
    NotFoundError,
    sha256_text,
)

ACTOR = "aret-mmu-playbook-v11-bootstrap"
DERIVED_TAG = "DERIVED_PLAYBOOK_V11"

SPECS: tuple[dict[str, Any], ...] = (
    {
        "title": "Playbook : méthode de travail ARET",
        "domain": "PLAYBOOK_METHOD",
        "content": (
            "Une tâche à la fois. Cycle obligatoire : reproduire → fixture minimale testable → implémenter → vérifier "
            "toutes les portes pertinentes → commit descriptif → mise à jour de la mémoire SQLite. Mesurer, ne pas "
            "affirmer : wallsweep priorise par impact. Borner puis pivoter : documenter un mur non généralisable et "
            "changer d’angle. Commits petits, fréquents et poussés : le conteneur est éphémère."
        ),
        "source_ids": ("CORE-0006",),
    },
    {
        "title": "Playbook : portes de validation et oracles",
        "domain": "PLAYBOOK_GATES",
        "content": (
            "Baseline transpile : hash comportemental 19acad982194bf07 ; tout changement strictement additif doit le "
            "laisser inchangé. Lift/structure : difftest + transpile diff ; sémantique CPU/lifter : cpudiff + funcdiff "
            "en plus ; HLE/OS/GUI large : winediff ; exception/SEH : ehdiff et gnuehdiff ; ABI/callee-pop : stdcall_audit. "
            "Une porte pertinente échouée ou absente interdit toute conclusion de support."
        ),
        "source_ids": ("CORE-0006", "CORE-0007"),
    },
    {
        "title": "Playbook : outillage CLI de diagnostic",
        "domain": "PLAYBOOK_TOOLING",
        "content": (
            "ARET_TRACE=1 : ring-buffer, chaîne d’appels et registres au crash. ARET_RELAY=1 avec WINEDEBUG=+relay, "
            "puis bench/relaydiff.py : première divergence API. ARET_DEBUG=1 : C généré avec -g, mapping gdb/winedbg. "
            "--mode walls sur un binaire ou wallsweep.sh sur un corpus : causes d’abort classées par binaires bloqués. "
            "Ces outils mesurent ; ils ne remplacent jamais une preuve différentielle admissible."
        ),
        "source_ids": ("INFRA-0003", "INDUS-0053", "INFRA-0017"),
    },
)


def _matching_derived(store: MemoryStore, title: str, domain: str) -> dict[str, Any] | None:
    with store._read_connection() as conn:
        rows = conn.execute(
            """SELECT k.id,k.type,k.status,k.title,k.content,k.content_hash
               FROM knowledge k
               JOIN knowledge_tag marker ON marker.knowledge_id=k.id AND marker.tag=?
               JOIN knowledge_tag domain_tag ON domain_tag.knowledge_id=k.id AND domain_tag.tag=?
               WHERE k.title=?
               ORDER BY k.id""",
            (DERIVED_TAG, domain, title),
        ).fetchall()
    if len(rows) > 1:
        raise AretError(f"Bootstrap Playbook V1.1 ambigu : plusieurs fiches dérivées pour {domain}")
    return dict(rows[0]) if rows else None


def _require_sources(store: MemoryStore, source_ids: tuple[str, ...]) -> None:
    with store._read_connection() as conn:
        missing = [
            source_id for source_id in source_ids
            if conn.execute("SELECT 1 FROM knowledge WHERE id=?", (source_id,)).fetchone() is None
        ]
    if missing:
        raise NotFoundError("Sources Playbook V1.1 introuvables : " + ", ".join(missing))


def _relation_exists(store: MemoryStore, from_id: str, to_id: str) -> bool:
    with store._read_connection() as conn:
        return conn.execute(
            """SELECT 1 FROM relation
               WHERE from_id=? AND relation_type='DERIVED_FROM' AND to_id=? AND status='ACTIVE'""",
            (from_id, to_id),
        ).fetchone() is not None


def apply(store: MemoryStore, actor: str = ACTOR) -> dict[str, Any]:
    """Applique V1.1 ; une seconde exécution ne crée ni fiche ni relation supplémentaire."""
    store._require_write()
    # Le noyau V1 est initialisé ici, explicitement hors du chemin de handoff.
    base = store._bootstrap_resume_playbook(actor)
    for spec in SPECS:
        _require_sources(store, tuple(spec["source_ids"]))

    report: dict[str, Any] = {
        "actor": actor,
        "base_playbook": base,
        "created": [],
        "existing": [],
        "relations_created": [],
        "relations_existing": [],
    }
    created_any = False
    for spec in SPECS:
        title = str(spec["title"])
        domain = str(spec["domain"])
        content = str(spec["content"])
        expected_hash = sha256_text(content)
        current = _matching_derived(store, title, domain)
        if current is None:
            created = store.append_knowledge(
                knowledge_type="RULE",
                status="ACTIVE",
                title=title,
                content=content,
                component_id="CORE",
                function_id=None,
                brick_id=None,
                tags=[CORE_PLAYBOOK_TAG, domain, DERIVED_TAG],
                proof_ids=[],
                supersedes_id=None,
                actor=actor,
                rebuild_index=False,
            )
            knowledge_id = str(created["id"])
            report["created"].append({"id": knowledge_id, "address": created["address"], "domain": domain})
            created_any = True
        else:
            if current["type"] != "RULE" or current["status"] != "ACTIVE" or current["content_hash"] != expected_hash:
                raise AretError(f"Fiche Playbook V1.1 existante incohérente : {current['id']}")
            knowledge_id = str(current["id"])
            report["existing"].append({"id": knowledge_id, "domain": domain})

        for source_id in tuple(spec["source_ids"]):
            if _relation_exists(store, knowledge_id, source_id):
                report["relations_existing"].append({"from_id": knowledge_id, "to_id": source_id})
                continue
            relation = store.add_relation(knowledge_id, "DERIVED_FROM", source_id, actor)
            report["relations_created"].append({"from_id": knowledge_id, "to_id": source_id, "address": relation["address"]})

    if created_any:
        report["index"] = store.rebuild_index(actor)
    else:
        report["index"] = {"rebuilt": False, "reason": "aucune fiche V1.1 nouvelle"}
    report["counts"] = {
        "created": len(report["created"]),
        "existing": len(report["existing"]),
        "relations_created": len(report["relations_created"]),
        "relations_existing": len(report["relations_existing"]),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap idempotent du Playbook opérationnel V1.1")
    parser.add_argument("--memory-dir", type=Path, default=PROJECT_ROOT / ".aret-memory")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = apply(MemoryStore(args.memory_dir, write_enabled=True))
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
