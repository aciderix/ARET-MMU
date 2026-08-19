"""Migration pilote ARET-MMU des sources documentaires de référence.

La migration est volontairement étroite : elle préserve le texte source, enregistre
la provenance exacte et ne promeut jamais une affirmation historique en PROVEN.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.repository import MemoryStore, canonical_json, utc_now

IMPORTER_VERSION = "aret-mmu-pilot/0.2.0"
SOURCE_REPOSITORY = "https://github.com/aciderix/Automatic-reverse-engineering-toolkit"


@dataclass(frozen=True)
class SourceSlice:
    path: str
    start_line: int
    end_line: int
    section: str
    knowledge_type: str
    status: str
    title: str
    component_id: str
    tags: tuple[str, ...]
    effective_at: str | None = None


PILOT_SLICES: tuple[SourceSlice, ...] = (
    SourceSlice(
        "docs/vision/70-reference-etat-methode-reste.md", 42, 63,
        "§0 — Objectif & principe sacré", "RULE", "ACTIVE",
        "Principe sacré : correct ou arrêt bruyant, jamais de faux silencieux", "CORE",
        ("DOCTRINE", "SOUNDNESS", "MIGRATED_70"),
    ),
    SourceSlice(
        "docs/vision/70-reference-etat-methode-reste.md", 240, 249,
        "§3 — État régression de référence", "STATE", "OBSERVED",
        "État de régression documenté : portes ARET de référence", "CORE",
        ("STATE", "ORACLE", "MEASUREMENT", "MIGRATED_70"), "2026-08-17",
    ),
    SourceSlice(
        "docs/vision/80-orientations-architecturales.md", 33, 47,
        "§1.1 — Fibers multithreading coopératif", "ARCHITECTURE", "ACTIVE",
        "Architecture retenue : threads coopératifs par fibers", "FIBER",
        ("ARCHITECTURE", "THREAD", "FIBER", "MIGRATED_80"), "2026-07-16",
    ),
    SourceSlice(
        "docs/vision/81-industrialisation.md", 18, 35,
        "§0 — Objectif et principe directeur", "DECISION", "ACTIVE",
        "Industrialisation : mesurer avant de coder, correct ou abort", "INDUS",
        ("INDUSTRIALISATION", "DECISION", "SOUNDNESS", "MIGRATED_81"), "2026-07-26",
    ),
    SourceSlice(
        "docs/vision/71-journal-de-bord.md", 8570, 8607,
        "2026-08-17 — HLE FS : volumes et chemins Unicode", "FORENSIC", "OBSERVED",
        "HLE : deuxième palier OS, incrément 1 — FS volumes et chemins Unicode", "HLE",
        ("HLE", "FS", "WIN32", "JOURNAL", "MIGRATED_71"), "2026-08-17",
    ),
    SourceSlice(
        "docs/vision/71-journal-de-bord.md", 8609, 8629,
        "2026-08-17 — HLE Shell : PIDL depuis un chemin", "FORENSIC", "OBSERVED",
        "HLE : deuxième palier OS, incrément 2 — PIDL shell depuis un chemin", "HLE",
        ("HLE", "SHELL", "WIN32", "JOURNAL", "MIGRATED_71"), "2026-08-17",
    ),
    SourceSlice(
        "docs/vision/71-journal-de-bord.md", 8631, 8655,
        "2026-08-17 — HLE Process : introspection process", "FORENSIC", "OBSERVED",
        "HLE : deuxième palier OS, incrément 3a — introspection process", "HLE",
        ("HLE", "PROCESS", "WIN32", "JOURNAL", "MIGRATED_71"), "2026-08-17",
    ),
    SourceSlice(
        "docs/vision/71-journal-de-bord.md", 8657, 8681,
        "2026-08-17 — HLE CRT/REG : reliquats CRT, registre et crypto", "FORENSIC", "OBSERVED",
        "HLE : deuxième palier OS, incrément 3b — CRT, registre et crypto", "HLE",
        ("HLE", "CRT", "REGISTRY", "CRYPTO", "JOURNAL", "MIGRATED_71"), "2026-08-17",
    ),
    SourceSlice(
        "docs/vision/71-journal-de-bord.md", 8683, 8719,
        "2026-08-17 — RECOV : spirv-cross et pointeur de fonction matérialisé", "FORENSIC", "OBSERVED",
        "RECOV : spirv-cross, récupération sound d’un pointeur de fonction matérialisé", "RECOV",
        ("RECOV", "AUTO_LIFT", "FUNCTION_POINTER", "JOURNAL", "MIGRATED_71"), "2026-08-17",
    ),
)

COMPONENTS = {
    "CORE": ("Noyau et doctrine ARET", "Principes généraux, pipelines, règles et état de régression."),
    "FIBER": ("Fibers et concurrence coopérative", "Architecture de threads coopératifs dans le runtime ARET."),
    "INDUS": ("Industrialisation", "Chantiers d’automatisation pilotés par mesure et oracles."),
    "HLE": ("High-Level Emulation", "Surface CRT et Win32 modélisée par le runtime ARET."),
    "RECOV": ("Récupération de fonctions", "Découverte sound de frontières et de cibles de fonctions."),
}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def git_revision(repository_root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository_root, text=True, encoding="utf-8"
    ).strip()


def read_slice(repository_root: Path, item: SourceSlice) -> tuple[str, str]:
    source_path = repository_root / item.path
    lines = source_path.read_text(encoding="utf-8").splitlines(keepends=True)
    if item.end_line > len(lines):
        raise ValueError(f"Plage source hors document : {item.path}:{item.start_line}-{item.end_line}")
    content = "".join(lines[item.start_line - 1 : item.end_line]).rstrip("\n")
    if not content.strip():
        raise ValueError(f"Extrait source vide : {item.path}:{item.start_line}-{item.end_line}")
    return content, sha256_text(content)


def build_manifest(repository_root: Path, revision: str) -> tuple[list[dict[str, Any]], str]:
    records: list[dict[str, Any]] = []
    for item in PILOT_SLICES:
        content, source_hash = read_slice(repository_root, item)
        records.append({"slice": asdict(item), "source_hash": source_hash, "content_hash": sha256_text(content)})
    manifest = {"repository": SOURCE_REPOSITORY, "revision": revision, "importer_version": IMPORTER_VERSION, "sources": records}
    return records, sha256_text(canonical_json(manifest))


def source_already_imported(store: MemoryStore, revision: str, item: SourceSlice) -> bool:
    with store._read_connection() as conn:
        return conn.execute(
            """SELECT 1 FROM knowledge_source WHERE source_revision=? AND source_path=?
               AND source_start_line=? AND source_end_line=? LIMIT 1""",
            (revision, item.path, item.start_line, item.end_line),
        ).fetchone() is not None


def ensure_batch(store: MemoryStore, revision: str, manifest_hash: str) -> str:
    batch_id = f"MIG-PILOT-{revision[:8].upper()}"
    with store._transaction() as conn:
        existing = conn.execute("SELECT * FROM migration_batch WHERE id=?", (batch_id,)).fetchone()
        if existing:
            if existing["source_manifest_hash"] != manifest_hash:
                raise RuntimeError("Le manifeste source du même lot de migration a changé ; créer un nouveau lot explicite.")
            return batch_id
        row = {
            "id": batch_id, "source_repository": SOURCE_REPOSITORY, "source_revision": revision,
            "importer_version": IMPORTER_VERSION, "started_at": utc_now(), "finished_at": None,
            "source_manifest_hash": manifest_hash, "status": "RUNNING", "summary_json": "{}",
        }
        conn.execute(
            """INSERT INTO migration_batch(id,source_repository,source_revision,importer_version,started_at,finished_at,
               source_manifest_hash,status,summary_json) VALUES(:id,:source_repository,:source_revision,:importer_version,
               :started_at,:finished_at,:source_manifest_hash,:status,:summary_json)""", row,
        )
        store._audit(conn, actor="aret-mmu-migrator", operation="START_MIGRATION_BATCH", entity_type="migration_batch", entity_id=batch_id, after=row)
    return batch_id


def finish_batch(store: MemoryStore, batch_id: str, summary: dict[str, Any], status: str = "COMPLETED") -> None:
    with store._transaction() as conn:
        before = dict(conn.execute("SELECT * FROM migration_batch WHERE id=?", (batch_id,)).fetchone())
        conn.execute(
            "UPDATE migration_batch SET status=?, finished_at=?, summary_json=? WHERE id=?",
            (status, utc_now(), canonical_json(summary), batch_id),
        )
        after = dict(conn.execute("SELECT * FROM migration_batch WHERE id=?", (batch_id,)).fetchone())
        store._audit(conn, actor="aret-mmu-migrator", operation="FINISH_MIGRATION_BATCH", entity_type="migration_batch", entity_id=batch_id, before=before, after=after)


def run(repository_root: Path, memory_dir: Path, dry_run: bool = False) -> dict[str, Any]:
    revision = git_revision(repository_root)
    manifest, manifest_hash = build_manifest(repository_root, revision)
    report: dict[str, Any] = {
        "repository": SOURCE_REPOSITORY, "revision": revision, "manifest_hash": manifest_hash,
        "importer_version": IMPORTER_VERSION, "dry_run": dry_run, "planned_items": len(PILOT_SLICES),
        "imported": [], "skipped_existing": [],
    }
    if dry_run:
        report["planned_sources"] = manifest
        return report
    store = MemoryStore(memory_dir, write_enabled=True)
    batch_id = ensure_batch(store, revision, manifest_hash)
    report["migration_batch_id"] = batch_id
    try:
        try:
            store.register_brick(
                "MIGRATION-PILOT-01", "Migration pilote documentaire", "ACTIVE", None,
                "Brique technique temporaire du Front pendant la migration pilote ARET-MMU.", "aret-mmu-migrator",
                "MIGRATION", None, 1,
            )
        except ValueError as exc:
            if "déjà existant" not in str(exc):
                raise
        for component_id, (title, description) in COMPONENTS.items():
            try:
                store.register_component(component_id, title, description, "aret-mmu-migrator")
            except ValueError as exc:
                if "déjà existant" not in str(exc):
                    raise
        for item in PILOT_SLICES:
            if source_already_imported(store, revision, item):
                report["skipped_existing"].append(f"{item.path}:{item.start_line}-{item.end_line}")
                continue
            content, source_hash = read_slice(repository_root, item)
            record = store.append_knowledge(
                knowledge_type=item.knowledge_type, status=item.status, title=item.title, content=content,
                component_id=item.component_id, function_id=None, brick_id=None, tags=item.tags,
                proof_ids=[], supersedes_id=None, actor="aret-mmu-migrator", effective_at=item.effective_at,
                document_source={
                    "repository": SOURCE_REPOSITORY, "revision": revision, "path": item.path,
                    "start_line": item.start_line, "end_line": item.end_line, "section": item.section,
                    "hash": source_hash, "migration_batch_id": batch_id,
                },
            )
            report["imported"].append({"address": record["address"], "title": record["title"], "source": record["sources"][0]})
        relevant_addresses = [item["address"] for item in report["imported"]]
        if relevant_addresses:
            store.update_front({
                "subsystem": "ARET-MMU documentation migration", "brick": "MIGRATION-PILOT-01",
                "current_wall": "Valider les objets migrés avant de granulariser l’intégralité du journal 71.",
                "last_action": "Migration pilote 70/71/80/81 effectuée avec provenance structurée.",
                "next_action": "Comparer les exports de contrôle, puis étendre à 82 et aux entrées antérieures du 71.",
                "relevant_1_address": relevant_addresses[0],
                "relevant_2_address": relevant_addresses[-1],
            }, "aret-mmu-migrator")
        report["front"] = store.get_front()
        finish_batch(store, batch_id, {"imported": len(report["imported"]), "skipped_existing": len(report["skipped_existing"]), "manifest_hash": manifest_hash})
    except Exception as exc:
        finish_batch(store, batch_id, {"error": str(exc), "imported": len(report["imported"])}, "FAILED")
        raise
    report_path = store.exports_dir / f"migration_pilot_{revision[:8]}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Migration pilote ARET-MMU 70/71/80/81")
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--memory-dir", type=Path, default=Path(__file__).resolve().parents[1] / ".aret-memory")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.repository_root.resolve(), args.memory_dir.resolve(), args.dry_run), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
