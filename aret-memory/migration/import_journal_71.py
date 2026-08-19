"""Importeur déterministe du journal chronologique 71 vers ARET-MMU.

Chaque sous-section datée de §3 est conservée comme un bloc source exact. Le parseur
ne résume pas et ne déduit aucune preuve ; les classifications restent volontairement
prudentes et sont dérivées de marqueurs explicites du titre uniquement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.repository import MemoryStore, canonical_json, utc_now
from migration.import_pilot import IMPORTER_VERSION, SOURCE_REPOSITORY, git_revision, sha256_text

JOURNAL_PATH = "docs/vision/71-journal-de-bord.md"
ENTRY_PATTERN = re.compile(r"^### (?P<date>\d{4}-\d{2}-\d{2}) — (?P<title>.+?)\s*$")
JOURNAL_SECTION_PATTERN = re.compile(r"^## 3\. Journal chronologique")


@dataclass(frozen=True)
class JournalEntry:
    date: str
    title: str
    start_line: int
    end_line: int
    content: str
    source_hash: str
    knowledge_type: str
    status: str
    component_id: str
    tags: tuple[str, ...]


COMPONENTS: dict[str, tuple[str, str]] = {
    "J71": ("Journal historique ARET", "Entrées chronologiques migrées depuis le document 71."),
    "ABI": ("ABI et modèle de pile", "Conventions d’appel, esp/ebp, callee-pop et frames."),
    "CORE": ("Noyau et doctrine ARET", "Règles, pipelines et état transversal."),
    "DEMO": ("Démonstrateurs", "Binaires et démonstrateurs de validation ARET."),
    "EH": ("Exceptions et unwind", "SEH, EH C++ et gestion des exceptions."),
    "GUI": ("Interface graphique", "Sous-systèmes USER/GDI et comportement GUI."),
    "HLE": ("High-Level Emulation", "Surface CRT, Win32 et API modélisée par ARET."),
    "INDUS": ("Industrialisation", "Automatisation, générateurs et passage à l’échelle."),
    "INFRA": ("Infrastructure et corpus", "Conteneur, outils, corpus et exécution."),
    "LIFT": ("Lifter et IR", "Sémantique d’instruction, SSA et émission."),
    "LOADER": ("Loader PE et modules", "Chargement, imports, DLL et rebasing."),
    "ORACLE": ("Oracles et validation", "Différentiels, corpus, mesures et portes de régression."),
    "RECOV": ("Récupération de fonctions", "Entrées de fonction, cibles indirectes et frontières."),
    "THREAD": ("Threads et fibers", "Concurrence coopérative et synchronisation."),
    "X87": ("x87 et flottants", "Pile FPU, arrondi et fallback runtime."),
}


def normalized_tag(raw: str) -> str | None:
    value = raw.upper().replace("✅", "").replace("🎯", "").strip()
    value = re.sub(r"[^A-Z0-9]+", "_", value).strip("_")
    if not value:
        return None
    return value[:56]


def header_tags(title: str) -> tuple[str, ...]:
    tags: set[str] = set()
    for bracket in re.findall(r"\[([^\]]+)\]", title):
        for raw in re.split(r"[/,]", bracket):
            tag = normalized_tag(raw.split()[0] if raw.split() else raw)
            if tag:
                tags.add(tag)
    return tuple(sorted(tags))


def component_for(tags: Iterable[str]) -> str:
    values = set(tags)
    priorities = (
        ("HLE", "HLE"), ("HLE_WIN32", "HLE"), ("HLE_CRT", "HLE"), ("HLE_FILE", "HLE"), ("HLE_STDIO", "HLE"),
        ("RECOV", "RECOV"), ("LOADER", "LOADER"), ("EH", "EH"), ("GUI", "GUI"), ("THREAD", "THREAD"),
        ("ABI", "ABI"), ("X87", "X87"), ("LIFT", "LIFT"), ("SSA", "LIFT"), ("ORACLE", "ORACLE"),
        ("INFRA", "INFRA"), ("DEMO", "DEMO"), ("INDUS", "INDUS"),
    )
    for tag, component in priorities:
        if tag in values:
            return component
    return "J71"


def classify(title: str, tags: tuple[str, ...]) -> tuple[str, str]:
    """N’utilise que des marqueurs littéraux du titre, jamais le contenu narratif."""
    upper = title.upper()
    if "DÉCISION UTILISATEUR" in upper or "DÉCISION" in upper:
        return "DECISION", "ACTIVE"
    if "MESURÉ" in upper or "SWEEP" in upper or "MESURE" in upper or "RÉGRESSION" in upper or "DIFFÉRENTIEL" in upper:
        return "MEASUREMENT", "OBSERVED"
    if "DÉCOUVERTE" in upper or "CONST" in upper and "MUR" in upper:
        return "DISCOVERY", "OBSERVED"
    return "FORENSIC", "OBSERVED"


def parse_journal(repository_root: Path) -> list[JournalEntry]:
    source = repository_root / JOURNAL_PATH
    lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
    start_of_journal = next((index + 1 for index, line in enumerate(lines) if JOURNAL_SECTION_PATTERN.match(line)), None)
    if start_of_journal is None:
        raise ValueError("La section chronologique §3 du document 71 est introuvable")
    markers: list[tuple[int, re.Match[str]]] = []
    for index, line in enumerate(lines, start=1):
        match = ENTRY_PATTERN.match(line.rstrip("\n"))
        if match and index > start_of_journal:
            markers.append((index, match))
    if not markers:
        raise ValueError("Aucune entrée datée n’a été trouvée dans le journal 71")
    entries: list[JournalEntry] = []
    for position, (start_line, match) in enumerate(markers):
        next_start = markers[position + 1][0] if position + 1 < len(markers) else len(lines) + 1
        end_line = next_start - 1
        while end_line >= start_line and not lines[end_line - 1].strip():
            end_line -= 1
        content = "".join(lines[start_line - 1 : end_line]).rstrip("\n")
        tags = header_tags(match.group("title"))
        knowledge_type, status = classify(match.group("title"), tags)
        entries.append(JournalEntry(
            date=match.group("date"), title=match.group("title"), start_line=start_line, end_line=end_line,
            content=content, source_hash=sha256_text(content), knowledge_type=knowledge_type, status=status,
            component_id=component_for(tags), tags=tuple(sorted({"JOURNAL", "MIGRATED_71", f"DATE_{match.group('date').replace('-', '')}", *tags})),
        ))
    return entries


def source_already_imported(store: MemoryStore, revision: str, entry: JournalEntry) -> bool:
    with store._read_connection() as conn:
        return conn.execute(
            """SELECT 1 FROM knowledge_source WHERE source_revision=? AND source_path=?
               AND source_start_line=? AND source_end_line=? AND source_hash=? LIMIT 1""",
            (revision, JOURNAL_PATH, entry.start_line, entry.end_line, entry.source_hash),
        ).fetchone() is not None


def ensure_batch(store: MemoryStore, revision: str, manifest_hash: str) -> str:
    batch_id = f"MIG-J71-{revision[:8].upper()}"
    with store._transaction() as conn:
        existing = conn.execute("SELECT * FROM migration_batch WHERE id=?", (batch_id,)).fetchone()
        if existing:
            if existing["source_manifest_hash"] != manifest_hash:
                raise RuntimeError("Le manifest du journal 71 a changé pour le même lot ; une révision de lot explicite est requise.")
            return batch_id
        row = {
            "id": batch_id, "source_repository": SOURCE_REPOSITORY, "source_revision": revision,
            "importer_version": "aret-mmu-journal71/0.3.0", "started_at": utc_now(), "finished_at": None,
            "source_manifest_hash": manifest_hash, "status": "RUNNING", "summary_json": "{}",
        }
        conn.execute(
            """INSERT INTO migration_batch(id,source_repository,source_revision,importer_version,started_at,finished_at,
               source_manifest_hash,status,summary_json) VALUES(:id,:source_repository,:source_revision,:importer_version,
               :started_at,:finished_at,:source_manifest_hash,:status,:summary_json)""", row,
        )
        store._audit(conn, actor="aret-mmu-journal71", operation="START_MIGRATION_BATCH", entity_type="migration_batch", entity_id=batch_id, after=row)
    return batch_id


def finish_batch(store: MemoryStore, batch_id: str, summary: dict[str, Any], status: str = "COMPLETED") -> None:
    with store._transaction() as conn:
        before = dict(conn.execute("SELECT * FROM migration_batch WHERE id=?", (batch_id,)).fetchone())
        conn.execute("UPDATE migration_batch SET status=?, finished_at=?, summary_json=? WHERE id=?", (status, utc_now(), canonical_json(summary), batch_id))
        after = dict(conn.execute("SELECT * FROM migration_batch WHERE id=?", (batch_id,)).fetchone())
        store._audit(conn, actor="aret-mmu-journal71", operation="FINISH_MIGRATION_BATCH", entity_type="migration_batch", entity_id=batch_id, before=before, after=after)


def rebuild_migration_front(store: MemoryStore, revision: str) -> dict[str, Any]:
    """Construit un Front de migration, sans prétendre deviner le chantier de code de l’utilisateur."""
    try:
        store.register_brick(
            "MIGRATION-J71-01", "Migration exhaustive du journal 71", "ACTIVE", None,
            "Brique technique temporaire du Front pendant la migration complète du journal historique 71.", "aret-mmu-journal71",
            "MIGRATION", None, 1,
        )
    except ValueError as exc:
        if "déjà existant" not in str(exc):
            raise
    with store._read_connection() as conn:
        total_entries = conn.execute(
            "SELECT COUNT(*) FROM knowledge_source WHERE source_revision=? AND source_path=?",
            (revision, JOURNAL_PATH),
        ).fetchone()[0]
        rows = conn.execute(
            """SELECT k.id, k.title, k.effective_at, s.source_start_line
               FROM knowledge k JOIN knowledge_source s ON s.knowledge_id=k.id
               WHERE s.source_revision=? AND s.source_path=?
               ORDER BY s.source_start_line DESC LIMIT 5""",
            (revision, JOURNAL_PATH),
        ).fetchall()
    if not rows:
        return store.get_front()
    updates: dict[str, str] = {
        "subsystem": "ARET-MMU journal 71 migration",
        "brick": "MIGRATION-J71-01",
        "current_wall": "Revue humaine de la classification historique avant migration des fiches consolidées et du tracker 82.",
        "last_action": f"Journal 71 migré de manière déterministe depuis la révision {revision[:8]}.",
        "next_action": "Valider le contrôle d’exhaustivité, puis importer le tracker vivant 82 et les mesures du corpus 90.",
        "journal_71_entry_count": str(total_entries),
        "journal_71_latest_address": f"ARET://knowledge/{rows[0]['id']}",
    }
    for index, row in enumerate(rows, start=1):
        updates[f"relevant_{index}_address"] = f"ARET://knowledge/{row['id']}"
    return store.update_front(updates, "aret-mmu-journal71")


def run(repository_root: Path, memory_dir: Path, dry_run: bool = False, limit: int | None = None) -> dict[str, Any]:
    revision = git_revision(repository_root)
    entries = parse_journal(repository_root)
    if limit is not None:
        if limit < 1:
            raise ValueError("La limite doit être positive")
        entries = entries[:limit]
    manifest = {
        "repository": SOURCE_REPOSITORY, "revision": revision, "importer_version": "aret-mmu-journal71/0.3.0",
        "source": JOURNAL_PATH, "entries": [
            {"date": entry.date, "start_line": entry.start_line, "end_line": entry.end_line, "source_hash": entry.source_hash,
             "type": entry.knowledge_type, "status": entry.status, "component": entry.component_id}
            for entry in entries
        ],
    }
    manifest_hash = sha256_text(canonical_json(manifest))
    report: dict[str, Any] = {
        "repository": SOURCE_REPOSITORY, "revision": revision, "source": JOURNAL_PATH, "manifest_hash": manifest_hash,
        "total_parsed": len(parse_journal(repository_root)), "planned": len(entries), "dry_run": dry_run,
        "classification": {}, "imported": [], "skipped_existing": [],
    }
    for entry in entries:
        report["classification"][entry.knowledge_type] = report["classification"].get(entry.knowledge_type, 0) + 1
    if dry_run:
        report["entries"] = [asdict(entry) | {"content": None} for entry in entries]
        return report

    store = MemoryStore(memory_dir, write_enabled=True)
    batch_id = ensure_batch(store, revision, manifest_hash)
    report["migration_batch_id"] = batch_id
    try:
        active_components = {entry.component_id for entry in entries}
        for component_id in sorted(active_components):
            title, description = COMPONENTS[component_id]
            try:
                store.register_component(component_id, title, description, "aret-mmu-journal71")
            except ValueError as exc:
                if "déjà existant" not in str(exc):
                    raise
        for entry in entries:
            if source_already_imported(store, revision, entry):
                report["skipped_existing"].append(f"{entry.start_line}-{entry.end_line}")
                continue
            record = store.append_knowledge(
                knowledge_type=entry.knowledge_type, status=entry.status, title=f"{entry.date} — {entry.title}",
                content=entry.content, component_id=entry.component_id, function_id=None, brick_id=None,
                tags=entry.tags, proof_ids=[], supersedes_id=None, actor="aret-mmu-journal71", effective_at=entry.date,
                document_source={
                    "repository": SOURCE_REPOSITORY, "revision": revision, "path": JOURNAL_PATH,
                    "start_line": entry.start_line, "end_line": entry.end_line, "section": entry.title,
                    "hash": entry.source_hash, "migration_batch_id": batch_id,
                },
                rebuild_index=False,
            )
            report["imported"].append(record["address"])
        rebuilt = store.rebuild_index("aret-mmu-journal71")
        report["index"] = rebuilt
        report["front"] = rebuild_migration_front(store, revision)
        finish_batch(store, batch_id, {
            "parsed": report["total_parsed"], "planned": len(entries), "imported": len(report["imported"]),
            "skipped_existing": len(report["skipped_existing"]), "manifest_hash": manifest_hash,
        })
    except Exception as exc:
        finish_batch(store, batch_id, {"error": str(exc), "imported": len(report["imported"])}, "FAILED")
        raise
    report_path = store.exports_dir / f"migration_journal_71_{revision[:8]}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrer le journal chronologique 71 vers ARET-MMU")
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--memory-dir", type=Path, default=Path(__file__).resolve().parents[1] / ".aret-memory")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, help="Importer seulement les N premières entrées pour un test contrôlé")
    args = parser.parse_args()
    print(json.dumps(run(args.repository_root.resolve(), args.memory_dir.resolve(), args.dry_run, args.limit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
