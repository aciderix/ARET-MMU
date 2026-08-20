"""Vérification exhaustive des migrations structurées ARET 82 et 90."""

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

from core.repository import MemoryStore
from migration.import_pilot import git_revision
from migration.import_trackers_82_90 import DOCUMENTS, extract_sections


def _stored_revision(conn: Any) -> str | None:
    """Retourne la dernière révision qui couvre simultanément les trackers 82 et 90."""
    rows = conn.execute(
        """SELECT source_revision, MAX(imported_at) AS latest_import
           FROM knowledge_source
           WHERE source_path IN (?, ?)
           GROUP BY source_revision
           HAVING COUNT(DISTINCT source_path)=2
           ORDER BY latest_import DESC, source_revision DESC""",
        DOCUMENTS,
    ).fetchall()
    return str(rows[0]["source_revision"]) if rows else None


def verify(repository_root: Path, memory_dir: Path) -> dict[str, Any]:
    working_tree_revision = git_revision(repository_root)
    expected = {path: {(item.start_line, item.end_line): item for item in extract_sections(repository_root, path)} for path in DOCUMENTS}
    store = MemoryStore(memory_dir, write_enabled=False)
    errors: list[str] = []
    document_counts: dict[str, int] = {}
    with store._read_connection() as conn:
        revision = _stored_revision(conn)
        if revision is None:
            errors.append("Aucune révision SQLite ne couvre les trackers 82/90")
            source_rows = []
            duplicates = []
            batch = None
        else:
            source_rows = [dict(row) for row in conn.execute(
                """SELECT ks.knowledge_id, ks.source_path, ks.source_start_line, ks.source_end_line, ks.source_hash,
                   k.content, k.content_hash, k.status
                   FROM knowledge_source ks JOIN knowledge k ON k.id=ks.knowledge_id
                   WHERE ks.source_revision=? AND ks.source_path IN (?, ?)
                   ORDER BY ks.source_path, ks.source_start_line""",
                (revision, *DOCUMENTS),
            )]
            duplicates = conn.execute(
                """SELECT source_path, source_start_line, source_end_line, COUNT(*) AS n FROM knowledge_source
                   WHERE source_revision=? AND source_path IN (?, ?) GROUP BY source_path, source_start_line, source_end_line HAVING n > 1""",
                (revision, *DOCUMENTS),
            ).fetchall()
            batch = conn.execute(
                "SELECT id, status, source_manifest_hash, summary_json FROM migration_batch WHERE id=?",
                (f"MIG-8290-{revision[:8].upper()}",),
            ).fetchone()
        fts_count = conn.execute("SELECT COUNT(*) FROM knowledge_fts").fetchone()[0]
        knowledge_count = conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
    for path, entries in expected.items():
        actual = [row for row in source_rows if row["source_path"] == path]
        document_counts[path] = len(actual)
        if len(actual) != len(entries):
            errors.append(f"{path} : {len(actual)} sources en base au lieu de {len(entries)}")
    if duplicates:
        errors.append(f"{len(duplicates)} plage(s) de provenance dupliquées")
    if fts_count != knowledge_count:
        errors.append(f"FTS : {fts_count} lignes pour {knowledge_count} connaissances")
    if batch is None or batch["status"] != "COMPLETED":
        errors.append("Lot MIG-8290 absent ou non terminé")
    for row in source_rows:
        item = expected[row["source_path"]].get((row["source_start_line"], row["source_end_line"]))
        if item is None:
            errors.append(f"Plage non attendue : {row['source_path']}:{row['source_start_line']}-{row['source_end_line']}")
            continue
        exact_hash = hashlib.sha256(item.content.encode("utf-8")).hexdigest()
        if row["content"] != item.content:
            errors.append(f"Contenu divergent : {row['knowledge_id']}")
        if row["source_hash"] != exact_hash or row["content_hash"] != exact_hash:
            errors.append(f"Hash divergent : {row['knowledge_id']}")
        if row["status"] == "PROVEN":
            errors.append(f"PROVEN interdit pour une migration documentaire : {row['knowledge_id']}")
    return {
        "ok": not errors, "revision": revision, "working_tree_revision": working_tree_revision, "expected_counts": {path: len(items) for path, items in expected.items()},
        "actual_counts": document_counts, "duplicate_source_ranges": len(duplicates),
        "knowledge_count": knowledge_count, "fts_count": fts_count,
        "migration_batch": dict(batch) if batch else None, "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Vérifier les migrations ARET 82 et 90")
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--memory-dir", type=Path, default=Path(__file__).resolve().parents[1] / ".aret-memory")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.repository_root.resolve(), args.memory_dir.resolve())
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
