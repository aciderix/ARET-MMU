"""Vérification d’intégrité et de couverture pour les documents ARET 70, 80 et 81."""

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
from migration.import_references_70_80_81 import DOCUMENTS, raw_sections


def is_substantive(line: str) -> bool:
    return bool(line.strip()) and line.strip() not in {"---", "***", "___"}


def covered(line_number: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= line_number <= end for start, end in ranges)


def _stored_revision(conn: Any) -> str | None:
    """Retourne la dernière révision qui couvre les trois sources de référence.

    La révision Git de l'arbre de travail évolue lors de tout commit ARET-MMU. Elle
    ne doit donc jamais être confondue avec la révision de provenance des objets
    documentaires déjà ingérés dans SQLite.
    """
    rows = conn.execute(
        """SELECT source_revision, MAX(imported_at) AS latest_import
           FROM knowledge_source
           WHERE source_path IN (?, ?, ?)
           GROUP BY source_revision
           HAVING COUNT(DISTINCT source_path)=3
           ORDER BY latest_import DESC, source_revision DESC""",
        DOCUMENTS,
    ).fetchall()
    return str(rows[0]["source_revision"]) if rows else None


def verify(repository_root: Path, memory_dir: Path) -> dict[str, Any]:
    working_tree_revision = git_revision(repository_root)
    store = MemoryStore(memory_dir, write_enabled=False)
    errors: list[str] = []
    document_counts: dict[str, int] = {}
    with store._read_connection() as conn:
        revision = _stored_revision(conn)
        if revision is None:
            errors.append("Aucune révision SQLite ne couvre les documents 70/80/81")
            rows = []
            duplicates = []
            batch = None
        else:
            rows = [dict(row) for row in conn.execute(
                """SELECT ks.knowledge_id, ks.source_path, ks.source_start_line, ks.source_end_line, ks.source_hash,
                   k.content, k.content_hash, k.status
                   FROM knowledge_source ks JOIN knowledge k ON k.id=ks.knowledge_id
                   WHERE ks.source_revision=? AND ks.source_path IN (?, ?, ?)
                   ORDER BY ks.source_path, ks.source_start_line, ks.source_end_line""",
                (revision, *DOCUMENTS),
            )]
            duplicates = conn.execute(
                """SELECT source_path, source_start_line, source_end_line, COUNT(*) AS n FROM knowledge_source
                   WHERE source_revision=? AND source_path IN (?, ?, ?)
                   GROUP BY source_path, source_start_line, source_end_line HAVING n > 1""",
                (revision, *DOCUMENTS),
            ).fetchall()
            batch = conn.execute(
                "SELECT id, status, source_manifest_hash, summary_json FROM migration_batch WHERE id=?",
                (f"MIG-708081-{revision[:8].upper()}",),
            ).fetchone()
        fts_count = conn.execute("SELECT COUNT(*) FROM knowledge_fts").fetchone()[0]
        knowledge_count = conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
    source_lines = {path: (repository_root / path).read_text(encoding="utf-8").splitlines(keepends=True) for path in DOCUMENTS}
    ranges_by_path: dict[str, list[tuple[int, int]]] = {path: [] for path in DOCUMENTS}
    for row in rows:
        path = row["source_path"]
        ranges_by_path[path].append((row["source_start_line"], row["source_end_line"]))
        if path not in source_lines:
            errors.append(f"Chemin de source inattendu : {path}")
            continue
        exact = "".join(source_lines[path][row["source_start_line"] - 1 : row["source_end_line"]]).rstrip("\n")
        exact_hash = hashlib.sha256(exact.encode("utf-8")).hexdigest()
        if row["content"] != exact:
            errors.append(f"Contenu divergent : {row['knowledge_id']}")
        if row["source_hash"] != exact_hash or row["content_hash"] != exact_hash:
            errors.append(f"Hash divergent : {row['knowledge_id']}")
        if row["status"] == "PROVEN":
            errors.append(f"PROVEN interdit pour une migration documentaire : {row['knowledge_id']}")
    for path in DOCUMENTS:
        ranges = ranges_by_path[path]
        document_counts[path] = len(ranges)
        for section in raw_sections(repository_root, path):
            for line_number in range(section.start_line, section.end_line + 1):
                if is_substantive(source_lines[path][line_number - 1]) and not covered(line_number, ranges):
                    errors.append(f"Ligne substantielle non couverte : {path}:{line_number}")
                    break
    if duplicates:
        errors.append(f"{len(duplicates)} plage(s) de provenance dupliquées")
    if fts_count != knowledge_count:
        errors.append(f"FTS : {fts_count} lignes pour {knowledge_count} connaissances")
    if batch is None or batch["status"] != "COMPLETED":
        errors.append("Lot MIG-708081 absent ou non terminé")
    return {
        "ok": not errors, "revision": revision, "working_tree_revision": working_tree_revision, "actual_counts": document_counts,
        "duplicate_source_ranges": len(duplicates), "knowledge_count": knowledge_count, "fts_count": fts_count,
        "migration_batch": dict(batch) if batch else None, "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Vérifier les références ARET 70/80/81")
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--memory-dir", type=Path, default=Path(__file__).resolve().parents[1] / ".aret-memory")
    parser.add_argument("--output", type=Path)
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
