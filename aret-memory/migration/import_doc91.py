#!/usr/bin/env python3
"""Préparation d’import pour la référence consolidée 91.

Le document 91 ne constitue pas la source canonique : la vue correspondante est reconstruite
par ``MemoryStore.export_reference_91``. Ce programme est réservé à l’arrivée ultérieure du
Markdown historique afin de l’enregistrer comme provenance vérifiable et de comparer sa
structure avec la vue reconstruite. Il ne fabrique jamais de contenu manquant.

Format attendu : un fichier UTF-8, par défaut ``docs/vision/91-reference-consolidee.md``,
commençant par un titre Markdown de niveau 1 contenant ``91`` et comportant des sections
``STATE``, ``RULE``, ``MEASUREMENT``, ``DECISION`` et/ou ``BRICK``. Toute différence est
signalée pour revue humaine ; l’import n’écrase aucune connaissance canonique.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

EXPECTED_SECTIONS = {"STATE", "RULE", "MEASUREMENT", "DECISION", "BRICK"}


class Document91Unavailable(FileNotFoundError):
    """La source historique 91 attendue n’a pas encore été versionnée."""


def inspect_source(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise Document91Unavailable(
            f"Document 91 indisponible : {path}. Ajoutez un Markdown UTF-8 respectant le format documenté "
            "dans migration/import_doc91.py ; aucune migration de substitution n’est exécutée."
        )
    text = path.read_text(encoding="utf-8")
    heading = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    if not heading or "91" not in heading.group(1):
        raise ValueError("Le document 91 doit commencer par un titre Markdown de niveau 1 contenant « 91 ».")
    sections = {match.group(1).strip().upper() for match in re.finditer(r"^##\s+(.+)$", text, flags=re.MULTILINE)}
    matching = sorted(section for section in sections if section in EXPECTED_SECTIONS)
    if not matching:
        raise ValueError("Le document 91 doit contenir au moins une section STATE, RULE, MEASUREMENT, DECISION ou BRICK.")
    return {
        "source": str(path.resolve()),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "title": heading.group(1).strip(),
        "recognized_sections": matching,
        "unrecognized_sections": sorted(sections - EXPECTED_SECTIONS),
        "action": "ready_for_provenance_comparison",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Vérifie la disponibilité et le format de la référence historique 91.")
    parser.add_argument("--source", type=Path, default=Path("docs/vision/91-reference-consolidee.md"))
    parser.add_argument("--json", action="store_true", help="Émet un rapport JSON exploitable en automatisation.")
    args = parser.parse_args()
    try:
        report = inspect_source(args.source)
    except (Document91Unavailable, UnicodeDecodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(f"Document 91 vérifié : {report['source']}")
        print(f"SHA-256 : {report['sha256']}")
        print("Sections reconnues : " + ", ".join(report["recognized_sections"]))
        print("Étape suivante : comparer ce document avec aret_export_reference_91 avant toute migration de provenance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
