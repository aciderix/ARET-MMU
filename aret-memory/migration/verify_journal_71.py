"""Contrôles d’exhaustivité et d’intégrité pour la migration du journal 71."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.repository import MemoryStore, canonical_json
from migration.import_journal_71 import JOURNAL_PATH, parse_journal
from migration.import_pilot import git_revision


def _stored_revision(conn: Any) -> str | None:
    """Retourne la dernière révision ayant importé le journal 71 complet."""
    row = conn.execute(
        """SELECT source_revision
           FROM knowledge_source
           WHERE source_path=?
           GROUP BY source_revision
           ORDER BY COUNT(*) DESC, MAX(imported_at) DESC, source_revision DESC
           LIMIT 1""",
        (JOURNAL_PATH,),
    ).fetchone()
    return str(row["source_revision"]) if row else None


def verify(repository_root: Path, memory_dir: Path) -> dict[str, Any]:
    working_tree_revision = git_revision(repository_root)
    parsed = parse_journal(repository_root)
    entries_by_range = {(entry.start_line, entry.end_line): entry for entry in parsed}
    store = MemoryStore(memory_dir, write_enabled=False)
    errors: list[str] = []
    with store._read_connection() as conn:
        revision = _stored_revision(conn)
        if revision is None:
            errors.append("Aucune révision SQLite ne couvre le journal 71")
            source_rows = []
            duplicate_ranges = []
            batch = None
        else:
            source_rows = [dict(row) for row in conn.execute(
                """SELECT ks.knowledge_id, ks.source_start_line, ks.source_end_line, ks.source_hash,
                   k.content, k.content_hash, k.status, k.type
                   FROM knowledge_source ks JOIN knowledge k ON k.id=ks.knowledge_id
                   WHERE ks.source_revision=? AND ks.source_path=?
                   ORDER BY ks.source_start_line""",
                (revision, JOURNAL_PATH),
            )]
            duplicate_ranges = conn.execute(
                """SELECT source_start_line, source_end_line, COUNT(*) AS n FROM knowledge_source
                   WHERE source_revision=? AND source_path=? GROUP BY source_start_line, source_end_line HAVING n > 1""",
                (revision, JOURNAL_PATH),
            ).fetchall()
            batch = conn.execute(
                "SELECT id, status, source_manifest_hash, summary_json FROM migration_batch WHERE id=?",
                (f"MIG-J71-{revision[:8].upper()}",),
            ).fetchone()
        fts_count = conn.execute("SELECT COUNT(*) FROM knowledge_fts").fetchone()[0]
        knowledge_count = conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
    if len(parsed) != 378:
        errors.append(f"Parseur : {len(parsed)} entrées au lieu de 378")
    if len(source_rows) != len(parsed):
        errors.append(f"Provenance : {len(source_rows)} entrées en base au lieu de {len(parsed)}")
    if duplicate_ranges:
        errors.append(f"Provenance dupliquée : {len(duplicate_ranges)} plage(s)")
    if fts_count != knowledge_count:
        errors.append(f"FTS non reconstructible en l’état : {fts_count} lignes FTS pour {knowledge_count} connaissances")
    if batch is None or batch["status"] != "COMPLETED":
        errors.append("Lot de migration journal 71 absent ou non terminé")
    for row in source_rows:
        entry = entries_by_range.get((row["source_start_line"], row["source_end_line"]))
        if entry is None:
            errors.append(f"Plage source inconnue en base : {row['source_start_line']}-{row['source_end_line']}")
            continue
        exact_hash = hashlib.sha256(entry.content.encode("utf-8")).hexdigest()
        if row["content"] != entry.content:
            errors.append(f"Contenu divergent : {row['knowledge_id']}")
        if row["source_hash"] != exact_hash or row["content_hash"] != exact_hash:
            errors.append(f"Hash divergent : {row['knowledge_id']}")
        if row["status"] == "PROVEN":
            errors.append(f"Promotion PROVEN interdite pour une source documentaire : {row['knowledge_id']}")
    report: dict[str, Any] = {
        "ok": not errors,
        "revision": revision,
        "working_tree_revision": working_tree_revision,
        "journal_entries_parsed": len(parsed),
        "journal_sources_in_store": len(source_rows),
        "duplicate_source_ranges": len(duplicate_ranges),
        "knowledge_count": knowledge_count,
        "fts_count": fts_count,
        "migration_batch": dict(batch) if batch else None,
        "errors": errors,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Vérifier l’intégrité de la migration ARET journal 71")
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--memory-dir", type=Path, default=Path(__file__).resolve().parents[1] / ".aret-memory")
    parser.add_argument("--output", type=Path, help="Rapport JSON facultatif")
    args = parser.parse_args()
    result = verify(args.repository_root.resolve(), args.memory_dir.resolve())
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
