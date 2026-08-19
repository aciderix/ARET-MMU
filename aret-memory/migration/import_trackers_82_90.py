"""Migration structurée, non chevauchante et prudente des documents vivants 82 et 90."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.repository import MemoryStore, canonical_json, utc_now
from migration.import_pilot import SOURCE_REPOSITORY, git_revision, sha256_text

DOCUMENTS = (
    "docs/vision/82-suivi-industrialisation.md",
    "docs/vision/90-corpus-sources.md",
)
HEADING = re.compile(r"^(?P<marks>#{2,3}) (?P<title>.+?)\s*$")
DATE = re.compile(r"(20\d{2}-\d{2}-\d{2})")

COMPONENTS = {
    "INDUS": ("Industrialisation", "Tracker des générateurs, jalons et chantiers automatisés."),
    "CORPUS": ("Corpus et mesures", "Sources de binaires, sweeps et murs mesurés."),
}


@dataclass(frozen=True)
class Section:
    path: str
    start_line: int
    end_line: int
    title: str
    level: int
    content: str
    source_hash: str
    knowledge_type: str
    status: str
    component_id: str
    tags: tuple[str, ...]
    effective_at: str | None


def document_code(path: str) -> str:
    return "82" if path.endswith("82-suivi-industrialisation.md") else "90"


def classify(path: str, title: str) -> tuple[str, str, str]:
    upper = title.upper()
    component = "INDUS" if document_code(path) == "82" else "CORPUS"
    if any(marker in upper for marker in ("PRINCIPE", "INVARIANT", "DOCTRINE")):
        return "RULE", "ACTIVE", component
    if any(marker in upper for marker in ("MESURE", "SWEEP", "RE-MESURE", "MUR", "RÉSIDU", "FAISABILITÉ", "PORTÉE", "ÉCHANTILLON")):
        return "MEASUREMENT", "OBSERVED", component
    if any(marker in upper for marker in ("PLAN COURANT", "PROCHAINS CRANS", "ROADMAP", "ÉTAT PAR PHASE", "RÉSULTAT")):
        return "STATE", "ACTIVE", component
    if document_code(path) == "90":
        return "STATE", "OBSERVED", component
    return "OBSERVATION", "OBSERVED", component


def extract_sections(repository_root: Path, path: str) -> list[Section]:
    lines = (repository_root / path).read_text(encoding="utf-8").splitlines(keepends=True)
    headings: list[tuple[int, int, str]] = []
    for line_number, line in enumerate(lines, start=1):
        match = HEADING.match(line.rstrip("\n"))
        if match:
            headings.append((line_number, len(match.group("marks")), match.group("title")))
    if not headings:
        raise ValueError(f"Aucun titre de niveau 2/3 : {path}")
    sections: list[Section] = []
    for index, (start_line, level, title) in enumerate(headings):
        if level == 2:
            next_level_two = next((line for line, other_level, _ in headings[index + 1 :] if other_level == 2), len(lines) + 1)
            first_child = next((line for line, other_level, _ in headings[index + 1 :] if other_level == 3 and line < next_level_two), None)
            end_line = (first_child - 1) if first_child else (next_level_two - 1)
        else:
            end_line = next((line - 1 for line, other_level, _ in headings[index + 1 :] if other_level <= level), len(lines))
        while end_line >= start_line and not lines[end_line - 1].strip():
            end_line -= 1
        content = "".join(lines[start_line - 1 : end_line]).rstrip("\n")
        if not content.strip() or content.strip() == f"{'#' * level} {title}":
            continue
        knowledge_type, status, component_id = classify(path, title)
        date = DATE.search(title)
        code = document_code(path)
        sections.append(Section(
            path=path, start_line=start_line, end_line=end_line, title=title, level=level,
            content=content, source_hash=sha256_text(content), knowledge_type=knowledge_type,
            status=status, component_id=component_id,
            tags=(f"DOC_{code}", f"MIGRATED_{code}", "TRACKER" if code == "82" else "CORPUS", f"LEVEL_{level}"),
            effective_at=date.group(1) if date else None,
        ))
    return sections


def parse_all(repository_root: Path) -> list[Section]:
    output: list[Section] = []
    for path in DOCUMENTS:
        output.extend(extract_sections(repository_root, path))
    return output


def source_already_imported(store: MemoryStore, revision: str, item: Section) -> bool:
    with store._read_connection() as conn:
        return conn.execute(
            """SELECT 1 FROM knowledge_source WHERE source_revision=? AND source_path=?
               AND source_start_line=? AND source_end_line=? AND source_hash=? LIMIT 1""",
            (revision, item.path, item.start_line, item.end_line, item.source_hash),
        ).fetchone() is not None


def ensure_batch(store: MemoryStore, revision: str, manifest_hash: str) -> str:
    batch_id = f"MIG-8290-{revision[:8].upper()}"
    with store._transaction() as conn:
        existing = conn.execute("SELECT * FROM migration_batch WHERE id=?", (batch_id,)).fetchone()
        if existing:
            if existing["source_manifest_hash"] != manifest_hash:
                raise RuntimeError("Le manifest 82/90 a changé pour ce lot ; créer un nouveau lot explicitement.")
            return batch_id
        row = {
            "id": batch_id, "source_repository": SOURCE_REPOSITORY, "source_revision": revision,
            "importer_version": "aret-mmu-trackers/0.4.0", "started_at": utc_now(), "finished_at": None,
            "source_manifest_hash": manifest_hash, "status": "RUNNING", "summary_json": "{}",
        }
        conn.execute(
            """INSERT INTO migration_batch(id,source_repository,source_revision,importer_version,started_at,finished_at,
               source_manifest_hash,status,summary_json) VALUES(:id,:source_repository,:source_revision,:importer_version,
               :started_at,:finished_at,:source_manifest_hash,:status,:summary_json)""", row,
        )
        store._audit(conn, actor="aret-mmu-trackers", operation="START_MIGRATION_BATCH", entity_type="migration_batch", entity_id=batch_id, after=row)
    return batch_id


def finish_batch(store: MemoryStore, batch_id: str, summary: dict[str, Any], status: str = "COMPLETED") -> None:
    with store._transaction() as conn:
        before = dict(conn.execute("SELECT * FROM migration_batch WHERE id=?", (batch_id,)).fetchone())
        conn.execute("UPDATE migration_batch SET status=?, finished_at=?, summary_json=? WHERE id=?", (status, utc_now(), canonical_json(summary), batch_id))
        after = dict(conn.execute("SELECT * FROM migration_batch WHERE id=?", (batch_id,)).fetchone())
        store._audit(conn, actor="aret-mmu-trackers", operation="FINISH_MIGRATION_BATCH", entity_type="migration_batch", entity_id=batch_id, before=before, after=after)


def update_migration_front(store: MemoryStore, revision: str) -> dict[str, Any]:
    with store._read_connection() as conn:
        counts = {
            path: conn.execute(
                "SELECT COUNT(*) FROM knowledge_source WHERE source_revision=? AND source_path=?", (revision, path)
            ).fetchone()[0]
            for path in DOCUMENTS
        }
        latest = conn.execute(
            """SELECT k.id FROM knowledge k JOIN knowledge_source s ON s.knowledge_id=k.id
               WHERE s.source_revision=? AND s.source_path IN (?, ?) ORDER BY s.source_path DESC, s.source_start_line DESC LIMIT 1""",
            (revision, *DOCUMENTS),
        ).fetchone()
    updates = {
        "migration_trackers_82_count": str(counts[DOCUMENTS[0]]),
        "migration_corpus_90_count": str(counts[DOCUMENTS[1]]),
        "last_action": "Trackers 82 et 90 migrés avec sections non chevauchantes, provenance et hashes.",
        "next_action": "Revue des sections tracker, puis migration exhaustive des références 70/80/81 et des archives selon besoin.",
    }
    if latest:
        updates["migration_82_90_latest_address"] = f"ARET://knowledge/{latest['id']}"
    return store.update_front(updates, "aret-mmu-trackers")


def run(repository_root: Path, memory_dir: Path, dry_run: bool = False) -> dict[str, Any]:
    revision = git_revision(repository_root)
    sections = parse_all(repository_root)
    manifest = {
        "repository": SOURCE_REPOSITORY, "revision": revision, "importer_version": "aret-mmu-trackers/0.4.0",
        "sections": [{"path": item.path, "start": item.start_line, "end": item.end_line, "hash": item.source_hash,
                      "type": item.knowledge_type, "status": item.status} for item in sections],
    }
    manifest_hash = sha256_text(canonical_json(manifest))
    report: dict[str, Any] = {
        "repository": SOURCE_REPOSITORY, "revision": revision, "manifest_hash": manifest_hash,
        "planned": len(sections), "by_document": {}, "classification": {}, "dry_run": dry_run,
        "imported": [], "skipped_existing": [],
    }
    for item in sections:
        report["by_document"][document_code(item.path)] = report["by_document"].get(document_code(item.path), 0) + 1
        report["classification"][item.knowledge_type] = report["classification"].get(item.knowledge_type, 0) + 1
    if dry_run:
        report["sections"] = [asdict(item) | {"content": None} for item in sections]
        return report

    store = MemoryStore(memory_dir, write_enabled=True)
    batch_id = ensure_batch(store, revision, manifest_hash)
    report["migration_batch_id"] = batch_id
    try:
        for component_id, (title, description) in COMPONENTS.items():
            try:
                store.register_component(component_id, title, description, "aret-mmu-trackers")
            except ValueError as exc:
                if "déjà existant" not in str(exc):
                    raise
        for item in sections:
            if source_already_imported(store, revision, item):
                report["skipped_existing"].append(f"{item.path}:{item.start_line}-{item.end_line}")
                continue
            record = store.append_knowledge(
                knowledge_type=item.knowledge_type, status=item.status, title=f"Doc {document_code(item.path)} — {item.title}",
                content=item.content, component_id=item.component_id, function_id=None, brick_id=None, tags=item.tags,
                proof_ids=[], supersedes_id=None, actor="aret-mmu-trackers", effective_at=item.effective_at,
                document_source={"repository": SOURCE_REPOSITORY, "revision": revision, "path": item.path,
                                 "start_line": item.start_line, "end_line": item.end_line, "section": item.title,
                                 "hash": item.source_hash, "migration_batch_id": batch_id},
                rebuild_index=False,
            )
            report["imported"].append(record["address"])
        report["index"] = store.rebuild_index("aret-mmu-trackers")
        report["front"] = update_migration_front(store, revision)
        finish_batch(store, batch_id, {"planned": len(sections), "imported": len(report["imported"]),
                                       "skipped_existing": len(report["skipped_existing"]), "manifest_hash": manifest_hash})
    except Exception as exc:
        finish_batch(store, batch_id, {"error": str(exc), "imported": len(report["imported"])}, "FAILED")
        raise
    report_path = store.exports_dir / f"migration_trackers_82_90_{revision[:8]}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrer les documents ARET 82 et 90")
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--memory-dir", type=Path, default=Path(__file__).resolve().parents[1] / ".aret-memory")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.repository_root.resolve(), args.memory_dir.resolve(), args.dry_run), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
