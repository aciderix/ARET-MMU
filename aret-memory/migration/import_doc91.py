#!/usr/bin/env python3
"""Statut non applicable de l’ancienne référence consolidée 91.

Le document 91 était une synthèse demandée à une autre IA à partir des documents 70, 71,
80, 81, 82, 83 et des informations importantes associées. Ces sources sont déjà migrées
avec provenance dans le Memory Store ; importer la synthèse créerait une redondance et
ne renforcerait aucune preuve.

La vue ``MemoryStore.export_reference_91`` reste disponible comme export dérivé de
commodité, compatible avec l’ancien numéro, mais aucune source Markdown 91 n’est
attendue, inspectée ou importée.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def inspect_source(path: Path) -> dict[str, object]:
    """Retourne le statut explicite d’une source 91, sans jamais l’importer."""
    return {
        "status": "NOT_APPLICABLE",
        "source": str(path.resolve()),
        "source_exists": path.is_file(),
        "reason": (
            "Le document 91 est une synthèse redondante des sources déjà migrées ; "
            "aucune migration de provenance ne doit être exécutée."
        ),
        "action": "use_aret_export_reference_91_for_derived_view",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Confirme que l’ancienne synthèse 91 est non applicable à la migration ARET-MMU."
    )
    parser.add_argument("--source", type=Path, default=Path("docs/vision/91-reference-consolidee.md"))
    parser.add_argument("--json", action="store_true", help="Émet un rapport JSON exploitable en automatisation.")
    args = parser.parse_args()
    report = inspect_source(args.source)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print("Document 91 : synthèse redondante, non applicable à la migration.")
        print("Action : utiliser aret_export_reference_91 pour une vue dérivée si nécessaire.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
