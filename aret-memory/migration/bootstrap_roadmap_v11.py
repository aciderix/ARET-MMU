#!/usr/bin/env python3
"""Classement idempotent V1.1 des briques ARET existantes.

Ce script ne crée ni ne supprime aucune brique et ne modifie pas son état. Il attribue
seulement les métadonnées de portfolio introduites par la migration 005 lorsque celles-ci
sont absentes ou correspondent encore au classement livré de référence.
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

from core.addressing import make_address
from core.repository import MemoryStore


ROADMAP_METADATA: dict[str, dict[str, object]] = {
    "AUTO-LIFT-02": {"milestone": "M7", "target_platform": "x86-pe32", "priority": 1},
    "M7-GUI": {"milestone": "M7", "target_platform": "x86-pe32", "priority": 1},
    "FIBERS-01": {"milestone": "M8", "target_platform": "x86-pe32", "priority": 2},
    "FIBERS-02": {"milestone": "M8", "target_platform": "x86-pe32", "priority": 3},
    "FIBERS-03": {"milestone": "M8", "target_platform": "x86-pe32", "priority": 3},
    "FIBERS-04": {"milestone": "M8", "target_platform": "x86-pe32", "priority": 4},
    "FIBERS-05": {"milestone": "M8", "target_platform": "x86-pe32", "priority": 4},
    "PHASE-A": {"milestone": "PHASE-A", "target_platform": None, "priority": 3},
    "PHASE-B": {"milestone": "PHASE-B", "target_platform": None, "priority": 4},
    "PHASE-C": {"milestone": "PHASE-C", "target_platform": None, "priority": 5},
}


def apply(store: MemoryStore, actor: str = "aret-roadmap-v11-bootstrap") -> dict[str, Any]:
    store._require_write()
    report: dict[str, Any] = {"updated": [], "unchanged": [], "missing": []}
    for brick_id, metadata in ROADMAP_METADATA.items():
        try:
            current = store.read(make_address("brick", brick_id))
        except Exception:
            report["missing"].append(brick_id)
            continue
        expected = dict(metadata)
        current_metadata = {key: current.get(key) for key in expected}
        if current_metadata == expected:
            report["unchanged"].append(brick_id)
            continue
        updated = store.update_brick(
            brick_id,
            state=None,
            milestone=expected["milestone"],  # type: ignore[arg-type]
            target_platform=expected["target_platform"],  # type: ignore[arg-type]
            priority=expected["priority"],  # type: ignore[arg-type]
            actor=actor,
        )
        report["updated"].append(updated["address"])
    report["counts"] = {key: len(value) for key, value in report.items() if isinstance(value, list)}
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap idempotent des métadonnées roadmap ARET-MMU V1.1")
    parser.add_argument("--memory-dir", default=".aret-memory")
    parser.add_argument("--actor", default="aret-roadmap-v11-bootstrap")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    store = MemoryStore(Path(args.memory_dir), write_enabled=True)
    report = apply(store, args.actor)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
