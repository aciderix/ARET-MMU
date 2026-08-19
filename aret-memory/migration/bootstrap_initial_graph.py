#!/usr/bin/env python3
"""Bootstrap prudent du graphe ARET-MMU à partir des connaissances déjà sourcées.

Aucune relation n'est déduite d'un modèle ou d'une similarité. Les liens ``CONCERNS``
sont créés exclusivement depuis les connaissances de type FORENSIC qui citent
littéralement l'un des symboles déclarés. La seule relation ``SUPERSEDES`` ajoutée
est l'invalidation explicitement formulée du premier fix ABI réverté par son correctif.
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

from core.repository import MemoryStore, make_address
from migration.bootstrap_roadmap_v11 import apply as apply_roadmap_metadata

ACTOR = "aret-mmu-graph-bootstrap"
FUNCTIONS: tuple[dict[str, str], ...] = (
    {"component_id": "EH", "module": "msvcrt", "symbol": "__except_handler3", "calling_convention": "cdecl"},
    {"component_id": "EH", "module": "msvcrt", "symbol": "_except_handler4_common", "calling_convention": "cdecl"},
    {"component_id": "EH", "module": "msvcrt", "symbol": "_EH_prolog3_GS", "calling_convention": "cdecl"},
    {"component_id": "HLE", "module": "user32", "symbol": "GetSysColor", "calling_convention": "stdcall"},
    {"component_id": "HLE", "module": "msvcrt", "symbol": "wcscat_s", "calling_convention": "cdecl"},
    {"component_id": "X87", "module": "msvcrt", "symbol": "_ftol2", "calling_convention": "cdecl"},
    {"component_id": "LIFT", "module": "winmerge", "symbol": "sub_470022", "calling_convention": "unknown"},
    {"component_id": "LIFT", "module": "winmerge", "symbol": "sub_867436", "calling_convention": "unknown"},
    {"component_id": "LIFT", "module": "winmerge", "symbol": "sub_85fd18", "calling_convention": "unknown"},
)
BRICKS: tuple[dict[str, str | None], ...] = (
    {"brick_id": "M7-GUI", "title": "Endgame GUI multi-modules MFC", "state": "ACTIVE", "component_id": "LIFT", "description": "Jalon M7-GUI : lifting et exécution de DLL MFC/GUI multi-modules."},
    {"brick_id": "AUTO-LIFT-02", "title": "Pré-lift et driver déterministe de DLL applicative", "state": "ACTIVE", "component_id": "LIFT", "description": "Brique de travail active du Front ARET pour le lifting de bibliothèques applicatives."},
    {"brick_id": "FIBERS-01", "title": "Fibers — fondation", "state": "PLANNED", "component_id": "CORE", "description": "Jalon FIBERS-01 enregistré à la demande de l’audit de production."},
    {"brick_id": "FIBERS-02", "title": "Fibers — continuité", "state": "PLANNED", "component_id": "CORE", "description": "Jalon FIBERS-02 enregistré à la demande de l’audit de production."},
    {"brick_id": "FIBERS-03", "title": "Fibers — propagation", "state": "PLANNED", "component_id": "CORE", "description": "Jalon FIBERS-03 enregistré à la demande de l’audit de production."},
    {"brick_id": "FIBERS-04", "title": "Fibers — intégration", "state": "PLANNED", "component_id": "CORE", "description": "Jalon FIBERS-04 enregistré à la demande de l’audit de production."},
    {"brick_id": "FIBERS-05", "title": "Fibers — validation", "state": "PLANNED", "component_id": "CORE", "description": "Jalon FIBERS-05 enregistré à la demande de l’audit de production."},
    {"brick_id": "PHASE-A", "title": "Phase A d’industrialisation", "state": "PLANNED", "component_id": None, "description": "Jalon de phase enregistré à la demande de l’audit de production."},
    {"brick_id": "PHASE-B", "title": "Phase B d’industrialisation", "state": "PLANNED", "component_id": None, "description": "Jalon de phase enregistré à la demande de l’audit de production."},
    {"brick_id": "PHASE-C", "title": "Phase C d’industrialisation", "state": "PLANNED", "component_id": None, "description": "Jalon de phase enregistré à la demande de l’audit de production."},
)
# Le texte de ABI-0005 déclare expressément le premier fix « REVERTÉ » ; ABI-0006 documente
# le correctif propre. Aucun autre remplacement historique n'est inféré par proximité de date.
CURATED_SUPERSEDES: tuple[tuple[str, str, str], ...] = (
    ("ABI-0006", "ABI-0005", "correctif ABI cross-block remplace le premier fix réverté"),
)
FRONT: dict[str, str] = {
    "subsystem": "DLL tierces C++ / Lifting",
    "brick": "AUTO-LIFT-02",
    "current_wall": "Lifting DLL applicatives tierces (LLVM, mbedTLS, ITK) et indirect call recovery",
    "last_action": "Graphe initial sourcé et Active Front d’ingénierie rétablis après migration documentaire.",
    "next_action": "Sélection pré-lift et driver déterministe sur première bibliothèque applicative",
    "relevant_1_address": "ARET://knowledge/ARCH-0003",
    "relevant_2_address": "ARET://knowledge/EH-0025",
    "relevant_3_address": "ARET://knowledge/X87-0003",
    "relevant_4_address": "ARET://knowledge/LIFT-0019",
    "relevant_5_address": "ARET://knowledge/RECOV-0021",
}


def function_id(spec: dict[str, str]) -> str:
    return f"{spec['component_id']}:{spec['module']}!{spec['symbol']}"


def function_exists(store: MemoryStore, stable_id: str) -> bool:
    with store._read_connection() as conn:
        return conn.execute("SELECT 1 FROM function_symbol WHERE id=?", (stable_id,)).fetchone() is not None


def knowledge_exists(store: MemoryStore, knowledge_id: str) -> bool:
    with store._read_connection() as conn:
        return conn.execute("SELECT 1 FROM knowledge WHERE id=?", (knowledge_id,)).fetchone() is not None


def brick_exists(store: MemoryStore, brick_id: str) -> bool:
    with store._read_connection() as conn:
        return conn.execute("SELECT 1 FROM brick WHERE id=?", (brick_id,)).fetchone() is not None


def literal_forensics(store: MemoryStore, symbol: str) -> list[str]:
    with store._read_connection() as conn:
        rows = conn.execute(
            """SELECT id FROM knowledge
               WHERE type='FORENSIC' AND (instr(lower(content), lower(?)) > 0 OR instr(lower(title), lower(?)) > 0)
               ORDER BY effective_at DESC, id""",
            (symbol, symbol),
        ).fetchall()
    return [str(row["id"]) for row in rows]


def relation_exists(store: MemoryStore, from_id: str, relation_type: str, to_id: str) -> bool:
    with store._read_connection() as conn:
        return conn.execute(
            "SELECT 1 FROM relation WHERE from_id=? AND relation_type=? AND to_id=?",
            (from_id, relation_type, to_id),
        ).fetchone() is not None


def bootstrap(store: MemoryStore, actor: str = ACTOR, replace_front: bool = True) -> dict[str, Any]:
    store._require_write()
    report: dict[str, Any] = {
        "actor": actor,
        "functions_created": [],
        "functions_existing": [],
        "bricks_created": [],
        "bricks_existing": [],
        "concerns_created": [],
        "concerns_existing": [],
        "supersedes_created": [],
        "supersedes_existing": [],
        "missing_required_knowledge": [],
    }
    for spec in FUNCTIONS:
        stable_id = function_id(spec)
        if function_exists(store, stable_id):
            report["functions_existing"].append(stable_id)
            continue
        created = store.register_function(actor=actor, **spec)
        report["functions_created"].append(created["address"])

    for spec in BRICKS:
        brick_id = str(spec["brick_id"])
        if brick_exists(store, brick_id):
            report["bricks_existing"].append(brick_id)
            continue
        created = store.register_brick(actor=actor, **spec)
        report["bricks_created"].append(created["address"])

    roadmap_metadata = apply_roadmap_metadata(store, actor=f"{actor}-roadmap")
    report["roadmap_metadata"] = roadmap_metadata

    for spec in FUNCTIONS:
        stable_id = function_id(spec)
        for knowledge_id in literal_forensics(store, spec["symbol"]):
            if relation_exists(store, knowledge_id, "CONCERNS", stable_id):
                report["concerns_existing"].append({"knowledge_id": knowledge_id, "function_id": stable_id})
                continue
            relation = store.add_relation(knowledge_id, "CONCERNS", stable_id, actor)
            report["concerns_created"].append({"knowledge_id": knowledge_id, "function_id": stable_id, "address": relation["address"]})

    for newer, older, reason in CURATED_SUPERSEDES:
        if not knowledge_exists(store, newer) or not knowledge_exists(store, older):
            report["missing_required_knowledge"].append({"newer": newer, "older": older, "reason": reason})
            continue
        if relation_exists(store, newer, "SUPERSEDES", older):
            report["supersedes_existing"].append({"newer": newer, "older": older, "reason": reason})
            continue
        relation = store.add_relation(newer, "SUPERSEDES", older, actor)
        report["supersedes_created"].append({"newer": newer, "older": older, "reason": reason, "address": relation["address"]})

    if replace_front:
        for address in [value for key, value in FRONT.items() if key.startswith("relevant_")]:
            store.read(address)
        current_values = {key: record["value"] for key, record in store.get_front()["state"].items()}
        if current_values == FRONT:
            report["front"] = store.get_front()
            report["front_unchanged"] = True
        else:
            report["front"] = store.replace_front(FRONT, actor)
            report["front_unchanged"] = False
    report["counts"] = {
        "functions_created": len(report["functions_created"]),
        "bricks_created": len(report["bricks_created"]),
        "concerns_created": len(report["concerns_created"]),
        "supersedes_created": len(report["supersedes_created"]),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap prudent du graphe et du Front ARET-MMU")
    parser.add_argument("--memory-dir", type=Path, default=PROJECT_ROOT / ".aret-memory")
    parser.add_argument("--no-replace-front", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = bootstrap(MemoryStore(args.memory_dir, write_enabled=True), replace_front=not args.no_replace_front)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
