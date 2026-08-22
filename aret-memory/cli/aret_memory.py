"""CLI ARET-MMU : inspection et maintenance explicites du Memory Store."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.repository import AretError, MemoryStore


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aret-memory", description="Administration explicite du Memory Store ARET-MMU")
    parser.add_argument("--memory-dir", type=Path, help="Répertoire .aret-memory à utiliser")
    parser.add_argument("--write-enabled", action="store_true", help="Autorise les mutations de maintenance demandées")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("boot", help="Afficher la doctrine et la configuration")
    commands.add_parser("show-front", help="Afficher l’Active Front")
    read = commands.add_parser("read", help="Lire une adresse ARET exacte")
    read.add_argument("address")
    find = commands.add_parser("find", help="Découvrir des candidats sans lire leur contenu")
    find.add_argument("--component")
    find.add_argument("--function")
    find.add_argument("--brick")
    find.add_argument("--type", dest="knowledge_type")
    find.add_argument("--status")
    find.add_argument("--tag")
    find.add_argument("--text")
    find.add_argument("--limit", type=int, default=20)
    proofs = commands.add_parser("show-proofs", help="Lister les preuves associées à une connaissance")
    proofs.add_argument("knowledge_id")
    related = commands.add_parser("related", help="Afficher les relations explicites d’un objet")
    related.add_argument("entity_id")
    related.add_argument("--type", dest="relation_type")
    related.add_argument("--direction", choices=("outgoing", "incoming", "both"), default="both")
    artifact = commands.add_parser("read-artifact", help="Lire un artefact de preuve après contrôle d’intégrité")
    artifact.add_argument("proof_id")
    artifact.add_argument("--max-bytes", type=int, default=65536)
    export = commands.add_parser("export", help="Créer une vue dérivée exportable")
    export.add_argument("--format", choices=("json", "markdown", "bundle"), default="json")
    export.add_argument("--name")
    bundle_export = commands.add_parser("export-bundle", help="Créer un Memory Bundle ZIP v2 vérifié")
    bundle_export.add_argument("--name")
    bundle_import = commands.add_parser("import-bundle", help="Importer un bundle vérifié dans un Store vide")
    bundle_import.add_argument("bundle_path", type=Path)
    bundle_import.add_argument("--actor", default="aret-cli-bundle-import")
    commands.add_parser("rebuild-index", help="Reconstruire FTS5 depuis les tables canoniques")
    audit = commands.add_parser("audit", help="Afficher les derniers événements d’audit")
    audit.add_argument("--limit", type=int, default=100)
    commands.add_parser("doctor", help="Vérifier la cohérence INTERNE de la mémoire (porte permanente ; exit≠0 si malsain)")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.memory_dir:
        os.environ["ARET_MEMORY_DIR"] = str(args.memory_dir)
    if args.write_enabled:
        os.environ["ARET_WRITE_ENABLED"] = "true"
    store = MemoryStore()
    try:
        if args.command == "boot":
            result = store.boot()
        elif args.command == "show-front":
            result = store.get_front()
        elif args.command == "read":
            result = store.read(args.address)
        elif args.command == "find":
            result = store.find(
                component_id=args.component, function_id=args.function, brick_id=args.brick,
                knowledge_type=args.knowledge_type, status=args.status, tag=args.tag, text=args.text, limit=args.limit,
            )
        elif args.command == "show-proofs":
            result = store.get_proofs(args.knowledge_id)
        elif args.command == "related":
            result = store.get_related(args.entity_id, args.relation_type, args.direction)
        elif args.command == "read-artifact":
            result = store.read_artifact(args.proof_id, args.max_bytes)
        elif args.command == "export":
            result = store.export(args.format, args.name)
        elif args.command == "export-bundle":
            result = store.export_bundle(args.name)
        elif args.command == "import-bundle":
            result = store.import_bundle(args.bundle_path, args.actor)
        elif args.command == "rebuild-index":
            result = store.rebuild_index()
        elif args.command == "audit":
            result = store.audit_events(args.limit)
        elif args.command == "doctor":
            result = store.health_report()
            emit(result)
            raise SystemExit(0 if result["ok"] else 1)
        else:  # pragma: no cover
            parser.error(f"Commande inconnue : {args.command}")
            return
        emit({"ok": True, "result": result})
    except AretError as exc:
        emit({"ok": False, "error": {"code": type(exc).__name__, "message": str(exc)}})
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
