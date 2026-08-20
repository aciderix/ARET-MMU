"""Référentiel SQLite transactionnel et append-first pour ARET-MMU."""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import re
import shutil
import sqlite3
import zipfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator, Sequence

from core.addressing import Address, make_address, parse_address

KNOWLEDGE_TYPES = {
    "RULE", "ARCHITECTURE", "DECISION", "FORENSIC", "OBSERVATION",
    "HYPOTHESIS", "STATE", "MEASUREMENT", "DISCOVERY",
}
KNOWLEDGE_STATUSES = {
    "ACTIVE", "PROVEN", "OBSERVED", "HYPOTHESIS", "SUPERSEDED",
    "OBSOLETE", "CONFLICTING",
}
BRICK_STATES = {"PLANNED", "ACTIVE", "BLOCKED", "DONE", "OBSOLETE"}
ROADMAP_VALUE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
RELATION_TYPES = {
    "VERIFIED_BY", "SUPERSEDES", "INFORMED_BY", "BLOCKED_BY", "IMPLEMENTS",
    "DERIVED_FROM", "CONCERNS", "APPLIES_TO", "CAUSED_BY", "EVOLVES_TO",
}
PROOF_RESULTS = {"PASS", "FAIL", "ERROR", "SKIPPED", "UNKNOWN"}
ID_RE = re.compile(r"^[A-Z][A-Z0-9_-]{1,31}$")
DEFAULT_MAX_ITEMS = 20
DEFAULT_MAX_BYTES = 65536
HARD_MAX_ITEMS = 100
HARD_MAX_BYTES = 262144


class AretError(ValueError):
    """Erreur métier retournable sans ambiguïté au client MCP."""


class NotFoundError(AretError):
    """Ressource canoniquement adressée mais absente."""


class WriteDisabledError(AretError):
    """Mutation refusée car le serveur fonctionne en lecture seule."""


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def as_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


class MemoryStore:
    """Source canonique de mémoire ARET, indépendante d’un LLM et du transport MCP."""

    def __init__(
        self,
        memory_dir: str | Path | None = None,
        *,
        write_enabled: bool | None = None,
        proof_hmac_secret: str | None = None,
    ) -> None:
        root = memory_dir or os.environ.get("ARET_MEMORY_DIR") or ".aret-memory"
        self.memory_dir = Path(root).expanduser().resolve()
        self.artifacts_dir = self.memory_dir / "artifacts"
        self.exports_dir = self.memory_dir / "exports"
        self.db_path = self.memory_dir / "aret_memory.sqlite"
        self.write_enabled = (
            write_enabled
            if write_enabled is not None
            else os.environ.get("ARET_WRITE_ENABLED", "false").lower() == "true"
        )
        self.proof_hmac_secret = proof_hmac_secret or os.environ.get("ARET_PROOF_HMAC_SECRET", "")
        self.last_sync_status: dict[str, Any] = {"enabled": False, "reason": "aucune synchronisation déclenchée"}
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def _connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _migrate(self) -> None:
        """Applique les migrations numérotées, avec checksum immuable par version."""
        schema_dir = Path(__file__).resolve().parents[1] / "schema"
        migrations: list[tuple[int, Path]] = []
        for candidate in schema_dir.glob("*.sql"):
            match = re.match(r"^(\d+)_.*\.sql$", candidate.name)
            if not match:
                continue
            migrations.append((int(match.group(1)), candidate))
        if not migrations or min(version for version, _ in migrations) != 1:
            raise RuntimeError("La migration initiale 001 est introuvable")
        if len({version for version, _ in migrations}) != len(migrations):
            raise RuntimeError("Versions de migration dupliquées")
        with self._connection() as conn:
            has_registry = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone() is not None
            applied = {
                int(row["version"]): row["checksum"]
                for row in conn.execute("SELECT version, checksum FROM schema_migrations").fetchall()
            } if has_registry else {}
            for version, migration_path in sorted(migrations):
                script = migration_path.read_text(encoding="utf-8")
                checksum = sha256_text(script)
                if version in applied:
                    if not hmac.compare_digest(applied[version], checksum):
                        raise RuntimeError(f"Checksum de migration modifié : {migration_path.name}")
                    continue
                conn.executescript(script)
                conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at, checksum) VALUES(?, ?, ?)",
                    (version, utc_now(), checksum),
                )
            latest_version = max(version for version, _ in migrations)
            defaults = {
                "memory_format_version": str(latest_version),
                "policy_version": "1",
                "core_doctrine": (
                    "SQLite est la source canonique. FIND découvre des candidats ; READ récupère "
                    "exactement les objets adressés. PROVEN exige une preuve PASS admissible. "
                    "Les connaissances sont append-first, leurs sources documentaires sont traçables, "
                    "et les artefacts lourds restent hors SQLite."
                ),
            }
            for key, value in defaults.items():
                current = conn.execute(
                    "SELECT value FROM store_metadata WHERE key=?", (key,)
                ).fetchone()
                if current is None:
                    conn.execute(
                        "INSERT INTO store_metadata(key, value, updated_at) VALUES(?, ?, ?)",
                        (key, value, utc_now()),
                    )
                elif current["value"] != value:
                    conn.execute(
                        "UPDATE store_metadata SET value=?, updated_at=? WHERE key=?",
                        (value, utc_now(), key),
                    )

    def _auto_sync_after_commit(self) -> None:
        """Synchronise après commit SQLite seulement si une politique locale l’active.

        Un échec Git ne rétrograde jamais une transaction mémoire déjà validée : il est conservé
        dans `last_sync_status` pour diagnostic et devra être résolu explicitement.
        """
        policy = self.memory_dir / "sync_policy.json"
        if not policy.exists():
            return
        try:
            from ops.git_memory import GitMemoryError, automatic_sync
            self.last_sync_status = automatic_sync(self.memory_dir.parent, str(self.memory_dir), "MUTATION")
        except (GitMemoryError, OSError, RuntimeError) as exc:
            self.last_sync_status = {"enabled": True, "committed": False, "refused": True, "reason": str(exc)}

    def checkpoint_wal(self) -> dict[str, int]:
        """Force un checkpoint WAL avant une opération qui sérialise ou versionne le fichier SQLite.

        Le refus explicite en cas de lecteur bloquant évite de prétendre qu’un fichier principal a été
        consolidé alors que SQLite signale qu’il ne peut pas tronquer son journal WAL.
        """
        conn = self._connection()
        try:
            row = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            busy, log_frames, checkpointed = (int(value) for value in row)
            if busy:
                raise AretError("Checkpoint WAL refusé : une connexion active empêche la consolidation SQLite")
            return {"busy": busy, "log_frames": log_frames, "checkpointed_frames": checkpointed}
        finally:
            conn.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self._connection()
        committed = False
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
            committed = True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        if committed:
            self._auto_sync_after_commit()

    @contextmanager
    def _read_connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connection()
        try:
            yield conn
        finally:
            conn.close()

    def _require_write(self) -> None:
        if not self.write_enabled:
            raise WriteDisabledError(
                "Le serveur ARET-MMU est en lecture seule. Définissez ARET_WRITE_ENABLED=true pour autoriser les mutations contrôlées."
            )

    @staticmethod
    def _normalise_tags(tags: Sequence[str] | None) -> list[str]:
        if not tags:
            return []
        output: set[str] = set()
        for raw in tags:
            tag = str(raw).strip().upper().replace(" ", "_")
            if not tag or len(tag) > 64 or not re.fullmatch(r"[A-Z0-9][A-Z0-9_.:-]*", tag):
                raise AretError(f"Tag invalide : {raw!r}")
            output.add(tag)
        return sorted(output)

    @staticmethod
    def _validate_identifier(identifier: str, label: str) -> str:
        candidate = str(identifier).strip().upper()
        if not ID_RE.fullmatch(candidate):
            raise AretError(f"{label} invalide : utilisez 2 à 32 caractères A-Z, 0-9, _ ou -")
        return candidate

    @staticmethod
    def _validate_document_source(source: dict[str, Any] | None) -> dict[str, Any] | None:
        """Valide une provenance textuelle sans lire ou interpréter le document source."""
        if source is None:
            return None
        required = {"repository", "revision", "path", "start_line", "end_line", "section", "hash"}
        missing = required - set(source)
        if missing:
            raise AretError(f"Provenance documentaire incomplète : {', '.join(sorted(missing))}")
        repository = str(source["repository"]).strip()
        revision = str(source["revision"]).strip()
        path = str(source["path"]).strip().replace("\\\\", "/")
        section = str(source["section"]).strip()
        source_hash = str(source["hash"]).strip().lower()
        try:
            start_line = int(source["start_line"])
            end_line = int(source["end_line"])
        except (TypeError, ValueError) as exc:
            raise AretError("Les lignes de provenance doivent être numériques") from exc
        if not repository or not revision or not path or path.startswith("/") or ".." in Path(path).parts:
            raise AretError("Référence de provenance documentaire invalide")
        if not section or start_line < 1 or end_line < start_line:
            raise AretError("Section ou plage de lignes de provenance invalide")
        if not re.fullmatch(r"[0-9a-f]{64}", source_hash):
            raise AretError("Le hash de provenance doit être un SHA-256 hexadécimal")
        batch_id = str(source.get("migration_batch_id", "")).strip() or None
        return {
            "repository": repository,
            "revision": revision,
            "path": path,
            "start_line": start_line,
            "end_line": end_line,
            "section": section,
            "hash": source_hash,
            "migration_batch_id": batch_id,
        }

    def _new_id(self, conn: sqlite3.Connection, entity: str, prefix: str) -> str:
        sequence = f"{entity}:{prefix}"
        row = conn.execute("SELECT next_value FROM id_sequence WHERE entity = ?", (sequence,)).fetchone()
        number = int(row["next_value"]) if row else 1
        if row:
            conn.execute("UPDATE id_sequence SET next_value = ? WHERE entity = ?", (number + 1, sequence))
        else:
            conn.execute("INSERT INTO id_sequence(entity, next_value) VALUES(?, ?)", (sequence, number + 1))
        return f"{prefix}-{number:04d}"

    def _audit(
        self,
        conn: sqlite3.Connection,
        *,
        actor: str,
        operation: str,
        entity_type: str,
        entity_id: str,
        before: Any = None,
        after: Any = None,
    ) -> str:
        event_id = self._new_id(conn, "audit", "A")
        conn.execute(
            """INSERT INTO audit_event(id, timestamp, actor, operation, entity_type, entity_id, payload_before, payload_after)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                utc_now(),
                actor,
                operation,
                entity_type,
                entity_id,
                canonical_json(before) if before is not None else None,
                canonical_json(after) if after is not None else None,
            ),
        )
        return event_id

    def record_session_checkpoint(
        self, event: str, session_id: str | None, trigger: str | None, compact_summary: str | None, actor: str
    ) -> dict[str, Any]:
        """Journalise un checkpoint de cycle de session sans enregistrer de résumé LLM comme connaissance."""
        self._require_write()
        event = event.strip().upper()
        if event not in {"PRE_COMPACT", "POST_COMPACT"}:
            raise AretError("Événement de checkpoint non autorisé")
        identity = (session_id or "unknown").strip()[:128] or "unknown"
        summary = (compact_summary or "").strip()
        if len(summary.encode("utf-8")) > 8192:
            raise AretError("compact_summary dépasse la borne de 8192 octets")
        with self._transaction() as conn:
            front = self._front_rows(conn)
            payload = {"event": event, "session_id": identity, "trigger": (trigger or "").strip()[:64],
                       "compact_summary": summary, "front": front}
            event_id = self._audit(conn, actor=actor, operation="SESSION_CHECKPOINT", entity_type="session", entity_id=identity, after=payload)
        return {"audit_id": event_id, "event": event, "session_id": identity, "front_keys": sorted(front)}

    def _metadata(self, conn: sqlite3.Connection) -> dict[str, str]:
        rows = conn.execute("SELECT key, value FROM store_metadata ORDER BY key").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def boot(self) -> dict[str, Any]:
        with self._read_connection() as conn:
            metadata = self._metadata(conn)
            return {
                "server": "ARET-MMU",
                "memory_dir": str(self.memory_dir),
                "database": str(self.db_path),
                "memory_format_version": metadata.get("memory_format_version", "1"),
                "policy_version": metadata.get("policy_version", "1"),
                "doctrine": metadata.get("core_doctrine", ""),
                "write_enabled": self.write_enabled,
                "proof_receipts_configured": bool(self.proof_hmac_secret),
                "sync_status": self.last_sync_status,
                "pagination": {
                    "default_max_items": DEFAULT_MAX_ITEMS,
                    "default_max_bytes": DEFAULT_MAX_BYTES,
                    "hard_max_items": HARD_MAX_ITEMS,
                    "hard_max_bytes": HARD_MAX_BYTES,
                },
                "front_address": "ARET://front/current",
            }

    def restore(self) -> dict[str, Any]:
        """Retourne le noyau de reprise : doctrine, version et Active Front, jamais le journal complet."""
        boot = self.boot()
        front = self.get_front()
        return {
            "doctrine": boot["doctrine"],
            "memory_format_version": boot["memory_format_version"],
            "policy_version": boot["policy_version"],
            "front": front,
            "front_address": boot["front_address"],
            "restore_contract": "FIND puis READ/READ_BATCH explicites pour les pages froides.",
        }

    def get_resume_brief(self, journal_limit: int = 8, rule_limit: int = 20, audit_limit: int = 12) -> dict[str, Any]:
        """Vue de reprise bornée : Front, règles actives, dernières entrées du journal 71 et audit récent.

        Cette vue dérivée ne lit aucun Markdown brut ; elle expose uniquement les objets sourcés et adressables
        du Store canonique. L’état Git reste volontairement hors SQLite.
        """
        for value, label, maximum in ((journal_limit, "journal_limit", 20), (rule_limit, "rule_limit", 40), (audit_limit, "audit_limit", 100)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > maximum:
                raise AretError(f"{label} doit être compris entre 1 et {maximum}")
        with self._read_connection() as conn:
            rules = [dict(row) for row in conn.execute(
                """SELECT id,title,status,updated_at FROM knowledge
                   WHERE type='RULE' AND status IN ('ACTIVE','PROVEN','OBSERVED')
                   ORDER BY updated_at DESC, id DESC LIMIT ?""", (rule_limit,)
            ).fetchall()]
            journal = [dict(row) for row in conn.execute(
                """SELECT DISTINCT k.id,k.title,k.type,k.status,k.updated_at,ks.source_path,ks.source_start_line,ks.source_end_line
                   FROM knowledge k JOIN knowledge_source ks ON ks.knowledge_id=k.id
                   WHERE ks.source_path LIKE '%71-journal-de-bord.md'
                   ORDER BY ks.source_start_line DESC, k.id DESC LIMIT ?""", (journal_limit,)
            ).fetchall()]
            audit = [dict(row) for row in conn.execute(
                """SELECT id,timestamp,actor,operation,entity_type,entity_id
                   FROM audit_event ORDER BY timestamp DESC, id DESC LIMIT ?""", (audit_limit,)
            ).fetchall()]
        for collection in (rules, journal):
            for row in collection:
                row["address"] = make_address("knowledge", row["id"])
        return {
            "restore": self.restore(), "rules": rules, "latest_document_71_entries": journal,
            "recent_audit": audit,
            "notice": "Les règles et entrées sont des pointeurs de reprise : utilisez READ/READ_BATCH pour leur contenu canonique intégral. Les commits Git sont fournis par le statut dépôt en lecture seule, jamais par SQLite.",
        }

    def get_resume_protocol(self, journal_limit: int = 8, batch_size: int = 20) -> dict[str, Any]:
        """Construit la lecture obligatoire après SessionStart ou compaction.

        Les documents de méthode et d’industrialisation explicitement demandés sont représentés
        par toutes leurs pages canonisées. Le journal 71 reste borné à ses dernières entrées.
        Les lots respectent la limite READ_BATCH et ne contiennent jamais de contenu inventé.
        """
        if isinstance(journal_limit, bool) or not isinstance(journal_limit, int) or journal_limit < 1 or journal_limit > 20:
            raise AretError("journal_limit doit être compris entre 1 et 20")
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1 or batch_size > DEFAULT_MAX_ITEMS:
            raise AretError(f"batch_size doit être compris entre 1 et {DEFAULT_MAX_ITEMS}")
        sources = (
            "docs/vision/70-reference-etat-methode-reste.md",
            "docs/vision/80-orientations-architecturales.md",
            "docs/vision/81-industrialisation.md",
            "docs/vision/82-suivi-industrialisation.md",
            "docs/vision/90-corpus-sources.md",
        )
        journal_source = "docs/vision/71-journal-de-bord.md"
        with self._read_connection() as conn:
            document_pages: dict[str, list[dict[str, Any]]] = {}
            for source_path in sources:
                rows = [dict(row) for row in conn.execute(
                    """SELECT DISTINCT k.id,k.title,k.type,k.status,ks.source_start_line,ks.source_end_line
                       FROM knowledge k JOIN knowledge_source ks ON ks.knowledge_id=k.id
                       WHERE ks.source_path=? ORDER BY ks.source_start_line ASC,k.id ASC""", (source_path,)
                ).fetchall()]
                for row in rows:
                    row["address"] = make_address("knowledge", row["id"])
                document_pages[source_path] = rows
            journal = [dict(row) for row in conn.execute(
                """SELECT DISTINCT k.id,k.title,k.type,k.status,ks.source_start_line,ks.source_end_line
                   FROM knowledge k JOIN knowledge_source ks ON ks.knowledge_id=k.id
                   WHERE ks.source_path=? ORDER BY ks.source_start_line DESC,k.id DESC LIMIT ?""", (journal_source, journal_limit)
            ).fetchall()]
        for row in journal:
            row["address"] = make_address("knowledge", row["id"])
        required_addresses = [
            row["address"] for source_path in sources for row in document_pages[source_path]
        ] + [row["address"] for row in journal]
        deduplicated = list(dict.fromkeys(required_addresses))
        batches = [deduplicated[index:index + batch_size] for index in range(0, len(deduplicated), batch_size)]
        return {
            "protocol_version": 1,
            "mandatory_documents": document_pages,
            "latest_document_71_entries": journal,
            "required_addresses": deduplicated,
            "required_read_batches": batches,
            "required_address_count": len(deduplicated),
            "batch_count": len(batches),
            "instructions": (
                "Barrière de reprise : lire tous les lots avec aret_read_batch avant toute opération non liée à la reprise. "
                "Les lectures sont contrôlées par le hook PreToolUse ; toute autre opération est refusée tant que la liste n’est pas épuisée."
            ),
        }

    def register_component(self, component_id: str, title: str, description: str, actor: str) -> dict[str, Any]:
        self._require_write()
        component_id = self._validate_identifier(component_id, "Identifiant de composant")
        if not title.strip():
            raise AretError("Le titre du composant est requis")
        with self._transaction() as conn:
            if conn.execute("SELECT 1 FROM component WHERE id = ?", (component_id,)).fetchone():
                raise AretError(f"Composant déjà existant : {component_id}")
            row = {
                "id": component_id,
                "title": title.strip(),
                "description": description.strip(),
                "created_at": utc_now(),
                "created_by": actor,
            }
            conn.execute(
                "INSERT INTO component(id, title, description, created_at, created_by) VALUES(:id,:title,:description,:created_at,:created_by)",
                row,
            )
            self._audit(conn, actor=actor, operation="REGISTER_COMPONENT", entity_type="component", entity_id=component_id, after=row)
        return self.read(make_address("component", component_id))

    def register_function(
        self, component_id: str, module: str, symbol: str, calling_convention: str, actor: str
    ) -> dict[str, Any]:
        self._require_write()
        component_id = self._validate_identifier(component_id, "Identifiant de composant")
        if not symbol.strip():
            raise AretError("Le symbole de fonction est requis")
        stable_id = f"{component_id}:{module.strip()}!{symbol.strip()}" if module.strip() else f"{component_id}:!{symbol.strip()}"
        if "/" in stable_id:
            raise AretError("Le symbole ne peut pas contenir de slash")
        with self._transaction() as conn:
            if not conn.execute("SELECT 1 FROM component WHERE id = ?", (component_id,)).fetchone():
                raise NotFoundError(f"Composant introuvable : {component_id}")
            if conn.execute("SELECT 1 FROM function_symbol WHERE id = ?", (stable_id,)).fetchone():
                raise AretError(f"Fonction déjà existante : {stable_id}")
            row = {
                "id": stable_id,
                "component_id": component_id,
                "module": module.strip(),
                "symbol": symbol.strip(),
                "calling_convention": calling_convention.strip(),
                "created_at": utc_now(),
                "created_by": actor,
            }
            conn.execute(
                """INSERT INTO function_symbol(id, component_id, module, symbol, calling_convention, created_at, created_by)
                   VALUES(:id,:component_id,:module,:symbol,:calling_convention,:created_at,:created_by)""",
                row,
            )
            self._audit(conn, actor=actor, operation="REGISTER_FUNCTION", entity_type="function", entity_id=stable_id, after=row)
        return self.read(make_address("function", stable_id))

    @staticmethod
    def _normalize_roadmap_value(value: str | None, label: str) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            return None
        if not ROADMAP_VALUE_RE.fullmatch(normalized):
            raise AretError(f"{label} invalide : utiliser 1 à 64 caractères [A-Za-z0-9._-]")
        return normalized

    @staticmethod
    def _normalize_priority(priority: int) -> int:
        if isinstance(priority, bool) or not isinstance(priority, int) or priority < 1 or priority > 5:
            raise AretError("priority doit être un entier entre 1 et 5")
        return priority

    def register_brick(
        self, brick_id: str, title: str, state: str, component_id: str | None, description: str, actor: str,
        milestone: str | None = None, target_platform: str | None = None, priority: int = 3,
    ) -> dict[str, Any]:
        self._require_write()
        brick_id = self._validate_identifier(brick_id, "Identifiant de brique")
        state = state.upper()
        if state not in BRICK_STATES:
            raise AretError(f"État de brique invalide : {state}")
        if not title.strip():
            raise AretError("Le titre de la brique est requis")
        if component_id:
            component_id = self._validate_identifier(component_id, "Identifiant de composant")
        milestone = self._normalize_roadmap_value(milestone, "milestone")
        target_platform = self._normalize_roadmap_value(target_platform, "target_platform")
        priority = self._normalize_priority(priority)
        with self._transaction() as conn:
            if component_id and not conn.execute("SELECT 1 FROM component WHERE id = ?", (component_id,)).fetchone():
                raise NotFoundError(f"Composant introuvable : {component_id}")
            if conn.execute("SELECT 1 FROM brick WHERE id = ?", (brick_id,)).fetchone():
                raise AretError(f"Brique déjà existante : {brick_id}")
            row = {
                "id": brick_id,
                "component_id": component_id,
                "title": title.strip(),
                "state": state,
                "description": description.strip(),
                "milestone": milestone,
                "target_platform": target_platform,
                "priority": priority,
                "created_at": utc_now(),
                "created_by": actor,
            }
            conn.execute(
                """INSERT INTO brick(id, component_id, title, state, description, milestone, target_platform, priority, created_at, created_by)
                   VALUES(:id,:component_id,:title,:state,:description,:milestone,:target_platform,:priority,:created_at,:created_by)""",
                row,
            )
            self._audit(conn, actor=actor, operation="REGISTER_BRICK", entity_type="brick", entity_id=brick_id, after=row)
        return self.read(make_address("brick", brick_id))

    def update_brick(
        self,
        brick_id: str,
        state: str | None,
        milestone: str | None,
        target_platform: str | None,
        priority: int | None,
        actor: str,
    ) -> dict[str, Any]:
        """Met à jour l’état et le classement d’une brique sans réécrire son identité ni son historique."""
        self._require_write()
        brick_id = self._validate_identifier(brick_id, "Identifiant de brique")
        if state is None and milestone is None and target_platform is None and priority is None:
            raise AretError("Au moins une propriété de brique doit être fournie")
        normalized_state = state.upper().strip() if state is not None else None
        if normalized_state is not None and normalized_state not in BRICK_STATES:
            raise AretError(f"État de brique invalide : {state}")
        normalized_milestone = self._normalize_roadmap_value(milestone, "milestone") if milestone is not None else None
        normalized_target = self._normalize_roadmap_value(target_platform, "target_platform") if target_platform is not None else None
        normalized_priority = self._normalize_priority(priority) if priority is not None else None
        with self._transaction() as conn:
            before = as_dict(conn.execute("SELECT * FROM brick WHERE id=?", (brick_id,)).fetchone())
            if before is None:
                raise NotFoundError(f"Brique introuvable : {brick_id}")
            after = {
                **before,
                "state": normalized_state if normalized_state is not None else before["state"],
                "milestone": normalized_milestone if milestone is not None else before.get("milestone"),
                "target_platform": normalized_target if target_platform is not None else before.get("target_platform"),
                "priority": normalized_priority if priority is not None else before["priority"],
            }
            if before["state"] == "ACTIVE" and after["state"] != "ACTIVE":
                front_brick = conn.execute("SELECT value FROM front_state WHERE key='brick'").fetchone()
                if front_brick is not None and front_brick["value"] == brick_id:
                    raise AretError("Remplacez d’abord le Front : il référence encore cette brique ACTIVE")
            conn.execute(
                "UPDATE brick SET state=?, milestone=?, target_platform=?, priority=? WHERE id=?",
                (after["state"], after["milestone"], after["target_platform"], after["priority"], brick_id),
            )
            self._audit(conn, actor=actor, operation="UPDATE_BRICK", entity_type="brick", entity_id=brick_id, before=before, after=after)
        return self.read(make_address("brick", brick_id))

    def _receipt_payload(
        self,
        *,
        kind: str,
        command: str,
        result: str,
        exit_code: int | None,
        artifact_path: str,
        artifact_hash: str,
        environment: dict[str, Any],
        started_at: str | None,
        finished_at: str | None,
    ) -> str:
        return canonical_json({
            "artifact_hash": artifact_hash,
            "artifact_path": artifact_path,
            "command": command,
            "environment": environment,
            "exit_code": exit_code,
            "finished_at": finished_at,
            "kind": kind,
            "result": result,
            "started_at": started_at,
        })

    def _validate_artifact(self, artifact_path: str, artifact_hash: str) -> tuple[str, int]:
        if not artifact_path:
            return "", 0
        candidate = (self.artifacts_dir / artifact_path).resolve()
        if self.artifacts_dir not in candidate.parents:
            raise AretError("Le chemin d’artefact doit rester sous .aret-memory/artifacts/")
        if not candidate.is_file():
            raise NotFoundError(f"Artefact introuvable : {artifact_path}")
        data_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if artifact_hash and not hmac.compare_digest(data_hash, artifact_hash):
            raise AretError("Le hash fourni ne correspond pas à l’artefact")
        return str(candidate.relative_to(self.artifacts_dir)), candidate.stat().st_size

    def record_proof(
        self,
        *,
        kind: str,
        command: str,
        result: str,
        exit_code: int | None,
        stdout_ref: str,
        stderr_ref: str,
        artifact_path: str,
        artifact_hash: str,
        environment: dict[str, Any] | None,
        started_at: str | None,
        finished_at: str | None,
        receipt_hmac: str,
        actor: str,
    ) -> dict[str, Any]:
        self._require_write()
        kind = kind.strip().upper()
        result = result.strip().upper()
        if not kind:
            raise AretError("Le type de preuve est requis")
        if result not in PROOF_RESULTS:
            raise AretError(f"Résultat de preuve invalide : {result}")
        environment = environment or {}
        relative_path, artifact_size = self._validate_artifact(artifact_path, artifact_hash)
        if relative_path:
            artifact_hash = hashlib.sha256((self.artifacts_dir / relative_path).read_bytes()).hexdigest()
        payload = self._receipt_payload(
            kind=kind, command=command, result=result, exit_code=exit_code,
            artifact_path=relative_path, artifact_hash=artifact_hash, environment=environment,
            started_at=started_at, finished_at=finished_at,
        )
        payload_hash = sha256_text(payload)
        expected_receipt = hmac.new(self.proof_hmac_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest() if self.proof_hmac_secret else ""
        admissible = int(bool(expected_receipt and receipt_hmac and hmac.compare_digest(expected_receipt, receipt_hmac)))
        with self._transaction() as conn:
            proof_id = self._new_id(conn, "proof", "P")
            row = {
                "id": proof_id, "kind": kind, "command": command, "result": result,
                "exit_code": exit_code, "stdout_ref": stdout_ref, "stderr_ref": stderr_ref,
                "artifact_path": relative_path, "artifact_hash": artifact_hash, "artifact_size": artifact_size,
                "environment_json": canonical_json(environment), "started_at": started_at,
                "finished_at": finished_at, "payload_hash": payload_hash, "receipt_hmac": receipt_hmac,
                "admissible": admissible, "created_at": utc_now(), "created_by": actor,
            }
            conn.execute(
                """INSERT INTO proof(id,kind,command,result,exit_code,stdout_ref,stderr_ref,artifact_path,artifact_hash,artifact_size,
                   environment_json,started_at,finished_at,payload_hash,receipt_hmac,admissible,created_at,created_by)
                   VALUES(:id,:kind,:command,:result,:exit_code,:stdout_ref,:stderr_ref,:artifact_path,:artifact_hash,:artifact_size,
                   :environment_json,:started_at,:finished_at,:payload_hash,:receipt_hmac,:admissible,:created_at,:created_by)""",
                row,
            )
            self._audit(conn, actor=actor, operation="RECORD_PROOF", entity_type="proof", entity_id=proof_id, after=row)
        return self.read(make_address("proof", proof_id))

    def attach_proof(self, knowledge_id: str, proof_id: str, actor: str, promote: bool = False) -> dict[str, Any]:
        """Lie une preuve existante et, si demandé, promeut seulement un PASS admissible."""
        self._require_write()
        with self._transaction() as conn:
            knowledge = self._knowledge_row(conn, knowledge_id)
            proof = conn.execute("SELECT * FROM proof WHERE id=?", (proof_id,)).fetchone()
            if proof is None:
                raise NotFoundError(f"Preuve introuvable : {proof_id}")
            before = dict(knowledge)
            stamp = utc_now()
            linked = conn.execute(
                "SELECT 1 FROM proof_link WHERE knowledge_id=? AND proof_id=?", (knowledge_id, proof_id)
            ).fetchone() is not None
            if not linked:
                conn.execute(
                    "INSERT INTO proof_link(knowledge_id,proof_id,linked_at,linked_by) VALUES(?,?,?,?)",
                    (knowledge_id, proof_id, stamp, actor),
                )
                self._insert_relation(conn, knowledge_id, "VERIFIED_BY", proof_id, actor)
            promoted = False
            if promote:
                if proof["result"] != "PASS" or not int(proof["admissible"]):
                    raise AretError("Promotion refusée : la preuve liée doit être PASS et admissible")
                if knowledge["status"] != "PROVEN":
                    conn.execute("UPDATE knowledge SET status='PROVEN', updated_at=? WHERE id=?", (stamp, knowledge_id))
                    promoted = True
            after = dict(conn.execute("SELECT * FROM knowledge WHERE id=?", (knowledge_id,)).fetchone())
            self._audit(
                conn, actor=actor, operation="ATTACH_PROOF", entity_type="knowledge", entity_id=knowledge_id,
                before=before, after={"knowledge": after, "proof_id": proof_id, "linked": not linked, "promoted": promoted},
            )
        return {"knowledge": self.read(make_address("knowledge", knowledge_id)), "proof": self.read(make_address("proof", proof_id)),
                "linked": not linked, "promoted": promoted}

    def invalidate_proof(self, proof_id: str, reason: str, actor: str) -> dict[str, Any]:
        """Retire l’admissibilité d’un proof et rétrograde les PROVEN devenus non justifiés."""
        self._require_write()
        if not reason.strip():
            raise AretError("Un motif d’invalidation est requis")
        demoted: list[str] = []
        with self._transaction() as conn:
            proof = conn.execute("SELECT * FROM proof WHERE id=?", (proof_id,)).fetchone()
            if proof is None:
                raise NotFoundError(f"Preuve introuvable : {proof_id}")
            before_proof = dict(proof)
            stamp = utc_now()
            conn.execute("UPDATE proof SET admissible=0 WHERE id=?", (proof_id,))
            after_proof = dict(conn.execute("SELECT * FROM proof WHERE id=?", (proof_id,)).fetchone())
            linked = conn.execute("SELECT knowledge_id FROM proof_link WHERE proof_id=? ORDER BY knowledge_id", (proof_id,)).fetchall()
            for row in linked:
                knowledge = self._knowledge_row(conn, row["knowledge_id"])
                if knowledge["status"] != "PROVEN":
                    continue
                still_valid = conn.execute(
                    """SELECT 1 FROM proof_link pl JOIN proof p ON p.id=pl.proof_id
                       WHERE pl.knowledge_id=? AND p.result='PASS' AND p.admissible=1 LIMIT 1""",
                    (knowledge["id"],),
                ).fetchone()
                if not still_valid:
                    before_knowledge = dict(knowledge)
                    conn.execute("UPDATE knowledge SET status='OBSERVED', updated_at=? WHERE id=?", (stamp, knowledge["id"]))
                    demoted.append(str(knowledge["id"]))
                    self._audit(
                        conn, actor=actor, operation="REEVALUATE_PROVEN_AFTER_PROOF_INVALIDATION",
                        entity_type="knowledge", entity_id=knowledge["id"], before=before_knowledge,
                        after={"status": "OBSERVED", "reason": f"proof {proof_id} invalidated"},
                    )
            self._audit(
                conn, actor=actor, operation="INVALIDATE_PROOF", entity_type="proof", entity_id=proof_id,
                before=before_proof, after={"proof": after_proof, "reason": reason.strip(), "demoted_knowledge": demoted},
            )
        return {"proof": self.read(make_address("proof", proof_id)), "demoted_knowledge_ids": demoted, "reason": reason.strip()}

    def _knowledge_row(self, conn: sqlite3.Connection, knowledge_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM knowledge WHERE id = ?", (knowledge_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Connaissance introuvable : {knowledge_id}")
        return row

    def _validate_proof_ids(self, conn: sqlite3.Connection, proof_ids: Sequence[str]) -> list[str]:
        ids = sorted(set(proof_ids))
        for proof_id in ids:
            if not conn.execute("SELECT 1 FROM proof WHERE id = ?", (proof_id,)).fetchone():
                raise NotFoundError(f"Preuve introuvable : {proof_id}")
        return ids

    def append_knowledge(
        self,
        *,
        knowledge_type: str,
        status: str | None,
        title: str,
        content: str,
        component_id: str | None,
        function_id: str | None,
        brick_id: str | None,
        tags: Sequence[str] | None,
        proof_ids: Sequence[str] | None,
        supersedes_id: str | None,
        actor: str,
        effective_at: str | None = None,
        document_source: dict[str, Any] | None = None,
        rebuild_index: bool = True,
    ) -> dict[str, Any]:
        self._require_write()
        knowledge_type = knowledge_type.upper()
        if knowledge_type not in KNOWLEDGE_TYPES:
            raise AretError(f"Type de connaissance invalide : {knowledge_type}")
        if not title.strip() or not content.strip():
            raise AretError("Le titre et le contenu sont requis")
        if status is None:
            status = "OBSERVED" if knowledge_type == "OBSERVATION" else "HYPOTHESIS" if knowledge_type == "HYPOTHESIS" else "ACTIVE"
        status = status.upper()
        if status not in KNOWLEDGE_STATUSES or status in {"SUPERSEDED", "OBSOLETE"}:
            raise AretError(f"Statut initial non autorisé : {status}")
        if component_id:
            component_id = self._validate_identifier(component_id, "Identifiant de composant")
        tags = self._normalise_tags(tags)
        proof_ids = list(proof_ids or [])
        effective_at = effective_at.strip() if effective_at else None
        source = self._validate_document_source(document_source)
        with self._transaction() as conn:
            if component_id and not conn.execute("SELECT 1 FROM component WHERE id = ?", (component_id,)).fetchone():
                raise NotFoundError(f"Composant introuvable : {component_id}")
            if function_id and not conn.execute("SELECT 1 FROM function_symbol WHERE id = ?", (function_id,)).fetchone():
                raise NotFoundError(f"Fonction introuvable : {function_id}")
            if brick_id and not conn.execute("SELECT 1 FROM brick WHERE id = ?", (brick_id,)).fetchone():
                raise NotFoundError(f"Brique introuvable : {brick_id}")
            previous = None
            version = 1
            if supersedes_id:
                previous = self._knowledge_row(conn, supersedes_id)
                version = int(previous["version"]) + 1
                if not component_id:
                    component_id = previous["component_id"]
            proof_ids = self._validate_proof_ids(conn, proof_ids)
            if status == "PROVEN":
                valid = conn.execute(
                    f"SELECT COUNT(*) AS n FROM proof WHERE id IN ({','.join('?' for _ in proof_ids)}) AND result='PASS' AND admissible=1",
                    proof_ids,
                ).fetchone()["n"] if proof_ids else 0
                if valid < 1:
                    raise AretError("PROVEN exige au moins une preuve PASS admissible et explicitement liée")
            prefix = component_id or "KN"
            knowledge_id = self._new_id(conn, "knowledge", prefix)
            created = utc_now()
            initial_status = "ACTIVE" if status == "PROVEN" else status
            row = {
                "id": knowledge_id, "type": knowledge_type, "status": initial_status,
                "title": title.strip(), "content": content, "component_id": component_id,
                "function_id": function_id, "brick_id": brick_id, "supersedes_id": supersedes_id,
                "effective_at": effective_at, "version": version, "content_hash": sha256_text(content), "created_at": created,
                "updated_at": created, "created_by": actor,
            }
            conn.execute(
                """INSERT INTO knowledge(id,type,status,title,content,component_id,function_id,brick_id,supersedes_id,effective_at,version,content_hash,created_at,updated_at,created_by)
                   VALUES(:id,:type,:status,:title,:content,:component_id,:function_id,:brick_id,:supersedes_id,:effective_at,:version,:content_hash,:created_at,:updated_at,:created_by)""",
                row,
            )
            for tag in tags:
                conn.execute("INSERT INTO knowledge_tag(knowledge_id, tag) VALUES(?, ?)", (knowledge_id, tag))
            if source:
                source_id = self._new_id(conn, "source", "S")
                source_row = {
                    "id": source_id, "knowledge_id": knowledge_id,
                    "source_repository": source["repository"], "source_revision": source["revision"],
                    "source_path": source["path"], "source_start_line": source["start_line"],
                    "source_end_line": source["end_line"], "source_section": source["section"],
                    "source_hash": source["hash"], "imported_at": created, "imported_by": actor,
                    "migration_batch_id": source["migration_batch_id"],
                }
                conn.execute(
                    """INSERT INTO knowledge_source(id,knowledge_id,source_repository,source_revision,source_path,source_start_line,
                       source_end_line,source_section,source_hash,imported_at,imported_by,migration_batch_id)
                       VALUES(:id,:knowledge_id,:source_repository,:source_revision,:source_path,:source_start_line,:source_end_line,
                       :source_section,:source_hash,:imported_at,:imported_by,:migration_batch_id)""", source_row,
                )
                self._audit(conn, actor=actor, operation="ATTACH_DOCUMENT_SOURCE", entity_type="knowledge_source", entity_id=source_id, after=source_row)
            for proof_id in proof_ids:
                conn.execute("INSERT INTO proof_link(knowledge_id, proof_id, linked_at, linked_by) VALUES(?, ?, ?, ?)", (knowledge_id, proof_id, created, actor))
                self._insert_relation(conn, knowledge_id, "VERIFIED_BY", proof_id, actor)
            if supersedes_id:
                self._insert_relation(conn, knowledge_id, "SUPERSEDES", supersedes_id, actor)
                conn.execute("UPDATE knowledge SET status='SUPERSEDED', updated_at=? WHERE id=?", (created, supersedes_id))
                self._audit(conn, actor=actor, operation="SUPERSEDE_KNOWLEDGE", entity_type="knowledge", entity_id=supersedes_id, before=as_dict(previous), after={"status": "SUPERSEDED", "superseded_by": knowledge_id})
            if status == "PROVEN":
                conn.execute("UPDATE knowledge SET status='PROVEN', updated_at=? WHERE id=?", (created, knowledge_id))
                row["status"] = "PROVEN"
            self._audit(conn, actor=actor, operation="APPEND_KNOWLEDGE", entity_type="knowledge", entity_id=knowledge_id, after={**row, "tags": tags, "proof_ids": proof_ids, "document_source": source})
            if rebuild_index:
                self._rebuild_fts(conn)
        return self.read(make_address("knowledge", knowledge_id))

    def _insert_relation(self, conn: sqlite3.Connection, from_id: str, relation_type: str, to_id: str, actor: str) -> str:
        relation_type = relation_type.upper()
        if relation_type not in RELATION_TYPES:
            raise AretError(f"Relation inconnue : {relation_type}")
        exists = conn.execute(
            "SELECT id FROM relation WHERE from_id=? AND relation_type=? AND to_id=?", (from_id, relation_type, to_id)
        ).fetchone()
        if exists:
            return str(exists["id"])
        relation_id = self._new_id(conn, "relation", "R")
        row = {"id": relation_id, "from_id": from_id, "relation_type": relation_type, "to_id": to_id, "status": "ACTIVE", "superseded_by": None, "created_at": utc_now(), "created_by": actor}
        conn.execute(
            "INSERT INTO relation(id,from_id,relation_type,to_id,status,superseded_by,created_at,created_by) VALUES(:id,:from_id,:relation_type,:to_id,:status,:superseded_by,:created_at,:created_by)", row
        )
        self._audit(conn, actor=actor, operation="ADD_RELATION", entity_type="relation", entity_id=relation_id, after=row)
        return relation_id

    def supersede_relation(
        self, relation_id: str, from_id: str, relation_type: str, to_id: str, actor: str
    ) -> dict[str, Any]:
        """Remplace une relation sans la modifier : la chaîne de supersession vit dans l’audit immuable."""
        self._require_write()
        if from_id == to_id:
            raise AretError("Une relation réflexive est interdite")
        with self._transaction() as conn:
            previous = as_dict(conn.execute("SELECT * FROM relation WHERE id=?", (relation_id,)).fetchone())
            if previous is None:
                raise NotFoundError(f"Relation à remplacer introuvable : {relation_id}")
            if previous["status"] != "ACTIVE":
                raise AretError(f"Relation déjà inactive : {relation_id}")
            if not self._entity_exists(conn, from_id) or not self._entity_exists(conn, to_id):
                raise NotFoundError("La nouvelle relation doit référencer deux entités existantes")
            if (previous["from_id"], previous["relation_type"], previous["to_id"]) == (from_id, relation_type.upper(), to_id):
                raise AretError("La relation de remplacement doit différer de la relation active")
            replacement_id = self._insert_relation(conn, from_id, relation_type, to_id, actor)
            conn.execute("UPDATE relation SET status='SUPERSEDED', superseded_by=? WHERE id=? AND status='ACTIVE'", (replacement_id, relation_id))
            superseded = as_dict(conn.execute("SELECT * FROM relation WHERE id=?", (relation_id,)).fetchone())
            self._audit(
                conn, actor=actor, operation="SUPERSEDE_RELATION", entity_type="relation", entity_id=relation_id,
                before=previous,
                after={"relation": superseded, "replacement_address": make_address("relation", replacement_id)},
            )
            replacement = as_dict(conn.execute("SELECT * FROM relation WHERE id=?", (replacement_id,)).fetchone())
        return {
            "superseded_relation": make_address("relation", relation_id),
            "replacement": {"address": make_address("relation", replacement_id), **(replacement or {})},
            "audit_operation": "SUPERSEDE_RELATION",
        }

    def _entity_exists(self, conn: sqlite3.Connection, entity_id: str) -> bool:
        tables = ("knowledge", "component", "function_symbol", "brick", "proof", "asset", "pipeline_run")
        return any(conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (entity_id,)).fetchone() for table in tables)

    def add_relation(self, from_id: str, relation_type: str, to_id: str, actor: str) -> dict[str, Any]:
        self._require_write()
        if from_id == to_id:
            raise AretError("Une relation réflexive est interdite en V1")
        with self._transaction() as conn:
            if not self._entity_exists(conn, from_id):
                raise NotFoundError(f"Source de relation introuvable : {from_id}")
            if not self._entity_exists(conn, to_id):
                raise NotFoundError(f"Cible de relation introuvable : {to_id}")
            relation_id = self._insert_relation(conn, from_id, relation_type, to_id, actor)
            row = as_dict(conn.execute("SELECT * FROM relation WHERE id=?", (relation_id,)).fetchone())
        return {"address": make_address("relation", relation_id), **(row or {})}

    def rebuild_front(self, actor: str = "aret-front-rebuild") -> dict[str, Any]:
        """Complète le Front avec des pointeurs dérivés, sans réécrire les clés de travail existantes."""
        self._require_write()
        with self._read_connection() as conn:
            proven = conn.execute(
                "SELECT id FROM knowledge WHERE status='PROVEN' ORDER BY updated_at DESC, id DESC LIMIT 1"
            ).fetchone()
            active = conn.execute(
                "SELECT id FROM knowledge WHERE status IN ('ACTIVE','OBSERVED','HYPOTHESIS') ORDER BY updated_at DESC, id DESC LIMIT 5"
            ).fetchall()
        addresses = [make_address("knowledge", row["id"]) for row in active]
        updates = {
            "front_reconstructed_at": utc_now(),
            "front_reconstructed_addresses": ", ".join(addresses),
        }
        if proven:
            updates["last_proven_increment"] = make_address("knowledge", proven["id"])
        front = self.update_front(updates, actor)
        return {"front": front, "derived_addresses": addresses, "last_proven_increment": updates.get("last_proven_increment")}

    def _validate_front_brick(self, conn: sqlite3.Connection, updates: dict[str, str]) -> None:
        """Le Front est le travail présent : il ne peut pas pointer vers une brique seulement planifiée."""
        if "brick" not in updates:
            return
        brick_id = updates["brick"]
        row = conn.execute("SELECT state FROM brick WHERE id=?", (brick_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Brique Front introuvable : {brick_id}")
        if row["state"] != "ACTIVE":
            raise AretError(f"Le Front doit référencer une brique ACTIVE, pas {brick_id} ({row['state']})")

    def update_front(self, updates: dict[str, str], actor: str) -> dict[str, Any]:
        self._require_write()
        if not updates or len(updates) > 20:
            raise AretError("Le Front requiert entre 1 et 20 clés")
        clean: dict[str, str] = {}
        for key, value in updates.items():
            safe_key = str(key).strip().lower().replace(" ", "_")
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", safe_key):
                raise AretError(f"Clé Front invalide : {key!r}")
            string_value = str(value).strip()
            if len(string_value.encode("utf-8")) > 4096:
                raise AretError(f"Valeur Front trop grande : {key!r}")
            clean[safe_key] = string_value
        with self._transaction() as conn:
            self._validate_front_brick(conn, clean)
            before = self._front_rows(conn)
            stamp = utc_now()
            for key, value in clean.items():
                conn.execute(
                    """INSERT INTO front_state(key,value,updated_at,updated_by) VALUES(?,?,?,?)
                       ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, updated_by=excluded.updated_by""",
                    (key, value, stamp, actor),
                )
            after = self._front_rows(conn)
            self._audit(conn, actor=actor, operation="UPDATE_FRONT", entity_type="front", entity_id="current", before=before, after=after)
        return self.get_front()

    def replace_front(self, updates: dict[str, str], actor: str) -> dict[str, Any]:
        """Remplace le contexte chaud entier, avec audit avant/après et sans effacer l’historique métier."""
        self._require_write()
        if not updates or len(updates) > 20:
            raise AretError("Le Front de remplacement requiert entre 1 et 20 clés")
        clean: dict[str, str] = {}
        for key, value in updates.items():
            safe_key = str(key).strip().lower().replace(" ", "_")
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", safe_key):
                raise AretError(f"Clé Front invalide : {key!r}")
            string_value = str(value).strip()
            if len(string_value.encode("utf-8")) > 4096:
                raise AretError(f"Valeur Front trop grande : {key!r}")
            clean[safe_key] = string_value
        with self._transaction() as conn:
            self._validate_front_brick(conn, clean)
            before = self._front_rows(conn)
            stamp = utc_now()
            conn.execute("DELETE FROM front_state")
            conn.executemany(
                "INSERT INTO front_state(key,value,updated_at,updated_by) VALUES(?,?,?,?)",
                [(key, value, stamp, actor) for key, value in sorted(clean.items())],
            )
            after = self._front_rows(conn)
            self._audit(conn, actor=actor, operation="REPLACE_FRONT", entity_type="front", entity_id="current", before=before, after=after)
        return self.get_front()

    def _front_rows(self, conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
        rows = conn.execute("SELECT key, value, updated_at, updated_by FROM front_state ORDER BY key").fetchall()
        return {row["key"]: {"value": row["value"], "updated_at": row["updated_at"], "updated_by": row["updated_by"]} for row in rows}

    def get_front(self) -> dict[str, Any]:
        with self._read_connection() as conn:
            state = self._front_rows(conn)
            addresses: list[str] = []
            for key, record in state.items():
                if key.endswith("_address") and record["value"].startswith("ARET://"):
                    try:
                        addresses.append(parse_address(record["value"]).canonical)
                    except ValueError:
                        continue
            return {"address": "ARET://front/current", "state": state, "relevant_addresses": sorted(set(addresses))}

    @staticmethod
    def _fts_phrase(text: str) -> str:
        terms = [term.replace('"', "") for term in text.split() if term.strip()]
        return " AND ".join(f'"{term}"' for term in terms)

    def find(
        self,
        *,
        component_id: str | None = None,
        function_id: str | None = None,
        brick_id: str | None = None,
        knowledge_type: str | None = None,
        status: str | None = None,
        tag: str | None = None,
        text: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        if limit < 1 or limit > HARD_MAX_ITEMS:
            raise AretError(f"Limite FIND invalide : 1 à {HARD_MAX_ITEMS}")
        filters_present = any([component_id, function_id, brick_id, knowledge_type, status, tag, text, created_after, created_before])
        if not filters_present:
            return {"items": [], "notice": "Aucun critère fourni : la découverte vide ne charge ni ne suppose aucune connaissance."}
        clauses: list[str] = []
        args: list[Any] = []
        joins = ""
        select_score = "NULL AS discovery_score"
        if text:
            phrase = self._fts_phrase(text)
            if not phrase:
                return {"items": [], "notice": "Critère textuel vide après normalisation."}
            joins = " JOIN knowledge_fts ON knowledge_fts.knowledge_id = k.id"
            clauses.append("knowledge_fts MATCH ?")
            args.append(phrase)
            select_score = "bm25(knowledge_fts) AS discovery_score"
        if component_id:
            clauses.append("k.component_id = ?")
            args.append(component_id)
        if function_id:
            clauses.append("k.function_id = ?")
            args.append(function_id)
        if brick_id:
            clauses.append("k.brick_id = ?")
            args.append(brick_id)
        if knowledge_type:
            kind = knowledge_type.upper()
            if kind not in KNOWLEDGE_TYPES:
                raise AretError(f"Type de connaissance invalide : {kind}")
            clauses.append("k.type = ?")
            args.append(kind)
        if status:
            state = status.upper()
            if state not in KNOWLEDGE_STATUSES:
                raise AretError(f"Statut de connaissance invalide : {state}")
            clauses.append("k.status = ?")
            args.append(state)
        if tag:
            normalised = self._normalise_tags([tag])[0]
            clauses.append("EXISTS (SELECT 1 FROM knowledge_tag kt WHERE kt.knowledge_id=k.id AND kt.tag=?)")
            args.append(normalised)
        if created_after:
            clauses.append("k.created_at >= ?")
            args.append(created_after)
        if created_before:
            clauses.append("k.created_at <= ?")
            args.append(created_before)
        query = f"""SELECT k.id, k.type, k.status, k.title, k.component_id, k.function_id, k.brick_id,
                     k.version, k.content_hash, k.created_at, k.updated_at, {select_score}
                     FROM knowledge k {joins} WHERE {' AND '.join(clauses)}
                     ORDER BY {'discovery_score ASC,' if text else ''} k.updated_at DESC, k.id ASC LIMIT ?"""
        args.append(limit)
        with self._read_connection() as conn:
            rows = [dict(row) for row in conn.execute(query, args).fetchall()]
        for item in rows:
            item["address"] = make_address("knowledge", item.pop("id"))
        return {
            "items": rows,
            "notice": "Résultats de découverte uniquement : utilisez aret_read ou aret_read_batch avec les adresses sélectionnées pour récupérer le contenu canonique.",
        }

    def _resource_row(self, conn: sqlite3.Connection, parsed: Address) -> dict[str, Any]:
        if parsed.resource_type == "knowledge":
            row = conn.execute("SELECT * FROM knowledge WHERE id=?", (parsed.identifier,)).fetchone()
            if row is None:
                raise NotFoundError(f"Connaissance introuvable : {parsed.identifier}")
            result = dict(row)
            result["tags"] = [item["tag"] for item in conn.execute("SELECT tag FROM knowledge_tag WHERE knowledge_id=? ORDER BY tag", (parsed.identifier,))]
            result["proof_ids"] = [item["proof_id"] for item in conn.execute("SELECT proof_id FROM proof_link WHERE knowledge_id=? ORDER BY proof_id", (parsed.identifier,))]
            result["sources"] = [
                dict(item) for item in conn.execute(
                    """SELECT id, source_repository, source_revision, source_path, source_start_line, source_end_line,
                       source_section, source_hash, imported_at, imported_by, migration_batch_id
                       FROM knowledge_source WHERE knowledge_id=? ORDER BY source_path, source_start_line, id""",
                    (parsed.identifier,),
                )
            ]
            result["address"] = parsed.canonical
            return result
        table = {
            "component": "component", "function": "function_symbol", "brick": "brick", "proof": "proof",
            "relation": "relation", "asset": "asset", "pipeline": "pipeline_run",
        }.get(parsed.resource_type)
        if table is None:
            raise NotFoundError(f"Ressource non lisible : {parsed.canonical}")
        row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (parsed.identifier,)).fetchone()
        if row is None:
            raise NotFoundError(f"Ressource introuvable : {parsed.canonical}")
        result = dict(row)
        result["address"] = parsed.canonical
        if parsed.resource_type == "proof":
            result["environment"] = json.loads(result.pop("environment_json"))
        elif parsed.resource_type == "asset":
            result["provenance"] = json.loads(result.pop("provenance_json"))
        elif parsed.resource_type == "pipeline":
            result["parameters"] = json.loads(result.pop("parameters_json"))
        return result

    def read(self, address: str) -> dict[str, Any]:
        parsed = parse_address(address)
        if parsed.resource_type == "front":
            return self.get_front()
        with self._read_connection() as conn:
            return self._resource_row(conn, parsed)

    def read_batch(self, addresses: Sequence[str], max_items: int = DEFAULT_MAX_ITEMS, max_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, Any]:
        if not addresses:
            raise AretError("READ_BATCH requiert au moins une adresse")
        if max_items < 1 or max_items > HARD_MAX_ITEMS or len(addresses) > max_items:
            raise AretError(f"READ_BATCH refuse plus de {min(max_items, HARD_MAX_ITEMS)} adresse(s)")
        if max_bytes < 1 or max_bytes > HARD_MAX_BYTES:
            raise AretError(f"max_bytes doit être compris entre 1 et {HARD_MAX_BYTES}")
        parsed = [parse_address(address) for address in addresses]
        duplicate_check = [address.canonical for address in parsed]
        if len(set(duplicate_check)) != len(duplicate_check):
            raise AretError("READ_BATCH n’accepte pas les adresses dupliquées")
        results: list[dict[str, Any]] = []
        total = 0
        with self._read_connection() as conn:
            for item in parsed:
                result = self.get_front() if item.resource_type == "front" else self._resource_row(conn, item)
                encoded_size = len(canonical_json(result).encode("utf-8"))
                if total + encoded_size > max_bytes:
                    raise AretError(f"READ_BATCH dépasse max_bytes ({max_bytes}) avant de lire {item.canonical}")
                results.append(result)
                total += encoded_size
        return {"items": results, "item_count": len(results), "byte_count": total, "max_bytes": max_bytes}

    def get_forensics(self, component_id: str | None, function_id: str | None, status: str | None, limit: int) -> dict[str, Any]:
        if not component_id and not function_id:
            raise AretError("Un composant ou une fonction est requis pour interroger les forensics")
        return self.find(component_id=component_id, function_id=function_id, knowledge_type="FORENSIC", status=status, limit=limit)

    def get_proofs(self, knowledge_id: str) -> dict[str, Any]:
        with self._read_connection() as conn:
            self._knowledge_row(conn, knowledge_id)
            rows = conn.execute(
                """SELECT p.* FROM proof p JOIN proof_link pl ON pl.proof_id=p.id
                   WHERE pl.knowledge_id=? ORDER BY p.created_at ASC, p.id ASC""",
                (knowledge_id,),
            ).fetchall()
            proofs = []
            for row in rows:
                item = dict(row)
                item["environment"] = json.loads(item.pop("environment_json"))
                item["address"] = make_address("proof", item["id"])
                proofs.append(item)
        return {"knowledge_address": make_address("knowledge", knowledge_id), "proofs": proofs}

    def _entity_address(self, conn: sqlite3.Connection, entity_id: str) -> str:
        """Retourne l’adresse stable d’une entité liée, sans jamais inventer son type."""
        for table, resource in (("knowledge", "knowledge"), ("component", "component"), ("function_symbol", "function"), ("brick", "brick"), ("proof", "proof"), ("relation", "relation"), ("asset", "asset"), ("pipeline_run", "pipeline")):
            if conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (entity_id,)).fetchone():
                return make_address(resource, entity_id)
        return entity_id

    def get_related(
        self, entity_id: str, relation_type: str | None = None, direction: str = "both", include_inactive: bool = False
    ) -> dict[str, Any]:
        if direction not in {"outgoing", "incoming", "both"}:
            raise AretError("Direction invalide : outgoing, incoming ou both")
        if relation_type and relation_type.upper() not in RELATION_TYPES:
            raise AretError(f"Relation inconnue : {relation_type}")
        filters: list[str] = []
        args: list[str] = []
        if direction == "outgoing":
            filters.append("from_id=?")
            args.append(entity_id)
        elif direction == "incoming":
            filters.append("to_id=?")
            args.append(entity_id)
        else:
            filters.append("(from_id=? OR to_id=?)")
            args.extend([entity_id, entity_id])
        if relation_type:
            filters.append("relation_type=?")
            args.append(relation_type.upper())
        if not include_inactive:
            filters.append("status='ACTIVE'")
        with self._read_connection() as conn:
            if not self._entity_exists(conn, entity_id):
                raise NotFoundError(f"Objet introuvable : {entity_id}")
            rows = [dict(row) for row in conn.execute(f"SELECT * FROM relation WHERE {' AND '.join(filters)} ORDER BY created_at, id", args)]
        return {"entity_id": entity_id, "direction": direction, "include_inactive": include_inactive, "relations": rows}

    def register_asset_file(
        self, *, source_path: Path, kind: str, source_kind: str, provenance: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        """Copie un asset autorisé sous le Store, le hashe et l’enregistre avec provenance."""
        self._require_write()
        if kind not in {"PE32", "DLL", "SNAPSHOT", "IAT_MAP", "CORPUS", "GENERATED", "TOOLCHAIN_REPORT"}:
            raise AretError("Type d’asset invalide")
        if source_kind not in {"LOCAL", "NETWORK", "GENERATED", "SNAPSHOT"}:
            raise AretError("Origine d’asset invalide")
        source = source_path.expanduser().resolve()
        if not source.is_file():
            raise NotFoundError(f"Asset source introuvable : {source}")
        size_bytes = source.stat().st_size
        if size_bytes > 2 * 1024 * 1024 * 1024:
            raise AretError("Asset refusé : taille supérieure à 2 GiB")
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", source.name)[:128] or "asset.bin"
        with self._transaction() as conn:
            asset_id = self._new_id(conn, "asset", "AS")
            relative_path = f"assets/{asset_id}_{safe_name}"
            destination = self.artifacts_dir / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            copied_hash = hashlib.sha256(destination.read_bytes()).hexdigest()
            if not hmac.compare_digest(source_hash, copied_hash):
                destination.unlink(missing_ok=True)
                raise AretError("Copie d’asset incohérente : hash source/destination différent")
            row = {
                "id": asset_id, "kind": kind, "source_kind": source_kind, "relative_path": relative_path,
                "sha256": copied_hash, "size_bytes": size_bytes, "provenance_json": canonical_json(provenance),
                "created_at": utc_now(), "created_by": actor,
            }
            conn.execute(
                """INSERT INTO asset(id,kind,source_kind,relative_path,sha256,size_bytes,provenance_json,created_at,created_by)
                   VALUES(:id,:kind,:source_kind,:relative_path,:sha256,:size_bytes,:provenance_json,:created_at,:created_by)""",
                row,
            )
            self._audit(conn, actor=actor, operation="REGISTER_ASSET", entity_type="asset", entity_id=asset_id, after=row)
        return self.read(make_address("asset", asset_id))

    def get_assets(self, kind: str | None = None, limit: int = 20) -> dict[str, Any]:
        """Retourne les assets canoniques disponibles sans charger leurs octets."""
        if limit < 1 or limit > HARD_MAX_ITEMS:
            raise AretError(f"Limite assets invalide : 1 à {HARD_MAX_ITEMS}")
        allowed = {"PE32", "DLL", "SNAPSHOT", "IAT_MAP", "CORPUS", "GENERATED", "TOOLCHAIN_REPORT"}
        clauses = ""
        args: list[Any] = []
        if kind is not None:
            normalized = str(kind).strip().upper()
            if normalized not in allowed:
                raise AretError("Type d’asset invalide")
            clauses = "WHERE kind=?"
            args.append(normalized)
        with self._read_connection() as conn:
            rows = [dict(row) for row in conn.execute(
                f"SELECT * FROM asset {clauses} ORDER BY created_at DESC, id DESC LIMIT ?", (*args, limit)
            ).fetchall()]
        for row in rows:
            row["provenance"] = json.loads(row.pop("provenance_json"))
            row["address"] = make_address("asset", row["id"])
        return {"kind": kind, "assets": rows}

    def record_pipeline_run(
        self, *, pipeline_name: str, kind: str, policy: str, result: str, command: str, parameters: dict[str, Any],
        artifact_path: str, artifact_hash: str, exit_code: int | None, started_at: str, finished_at: str, actor: str,
    ) -> dict[str, Any]:
        """Journalise une exécution de pipeline fermé, avec l’artefact déjà hashé sous le Store."""
        self._require_write()
        normalized_name = str(pipeline_name).strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,95}", normalized_name):
            raise AretError("Nom de pipeline invalide")
        if policy not in {"READ_ONLY", "GENERATE", "NETWORK", "SENSITIVE"}:
            raise AretError("Politique de pipeline invalide")
        if result not in {"PASS", "FAIL", "ERROR", "SKIPPED", "UNKNOWN", "PLANNED"}:
            raise AretError("Résultat de pipeline invalide")
        serialized_parameters = canonical_json(parameters)
        if len(serialized_parameters.encode("utf-8")) > 16384:
            raise AretError("Paramètres de pipeline trop volumineux")
        relative_path, _ = self._validate_artifact(artifact_path, artifact_hash)
        if not relative_path:
            raise AretError("Une exécution de pipeline exige un artefact")
        verified_hash = hashlib.sha256((self.artifacts_dir / relative_path).read_bytes()).hexdigest()
        with self._transaction() as conn:
            run_id = self._new_id(conn, "pipeline_run", "PR")
            row = {
                "id": run_id, "pipeline_name": normalized_name, "kind": str(kind).strip().upper(), "policy": policy,
                "result": result, "command": command, "parameters_json": serialized_parameters,
                "artifact_path": relative_path, "artifact_hash": verified_hash, "exit_code": exit_code,
                "started_at": started_at, "finished_at": finished_at, "created_at": utc_now(), "created_by": actor,
            }
            conn.execute(
                """INSERT INTO pipeline_run(id,pipeline_name,kind,policy,result,command,parameters_json,artifact_path,artifact_hash,
                   exit_code,started_at,finished_at,created_at,created_by)
                   VALUES(:id,:pipeline_name,:kind,:policy,:result,:command,:parameters_json,:artifact_path,:artifact_hash,
                   :exit_code,:started_at,:finished_at,:created_at,:created_by)""",
                row,
            )
            self._audit(conn, actor=actor, operation="RUN_PIPELINE", entity_type="pipeline", entity_id=run_id, after=row)
        return self.read(make_address("pipeline", run_id))

    def get_pipeline_runs(self, pipeline_name: str | None = None, limit: int = 12) -> dict[str, Any]:
        """Retourne les derniers pipelines exécutés, sans charger leurs artefacts lourds."""
        if limit < 1 or limit > HARD_MAX_ITEMS:
            raise AretError(f"Limite pipeline invalide : 1 à {HARD_MAX_ITEMS}")
        clauses: list[str] = []
        args: list[Any] = []
        if pipeline_name is not None:
            name = str(pipeline_name).strip().lower()
            if not re.fullmatch(r"[a-z][a-z0-9_]{1,95}", name):
                raise AretError("Nom de pipeline invalide")
            clauses.append("pipeline_name=?")
            args.append(name)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._read_connection() as conn:
            rows = [dict(row) for row in conn.execute(
                f"SELECT * FROM pipeline_run {where} ORDER BY created_at DESC, id DESC LIMIT ?", (*args, limit)
            ).fetchall()]
        for row in rows:
            row["parameters"] = json.loads(row.pop("parameters_json"))
            row["address"] = make_address("pipeline", row["id"])
        return {"pipeline_name": pipeline_name, "runs": rows}

    def read_pipeline_artifact(self, pipeline_run_id: str, max_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, Any]:
        """Lit l’artefact hashé d’un pipeline après vérification d’intégrité et borne de taille."""
        if max_bytes < 1 or max_bytes > HARD_MAX_BYTES:
            raise AretError(f"max_bytes doit être compris entre 1 et {HARD_MAX_BYTES}")
        with self._read_connection() as conn:
            row = conn.execute("SELECT artifact_path, artifact_hash FROM pipeline_run WHERE id=?", (pipeline_run_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"Pipeline introuvable : {pipeline_run_id}")
            path = (self.artifacts_dir / row["artifact_path"]).resolve()
            if self.artifacts_dir not in path.parents or not path.is_file():
                raise AretError("Référence d’artefact pipeline hors périmètre ou absente")
            data = path.read_bytes()
            actual_hash = hashlib.sha256(data).hexdigest()
            if not hmac.compare_digest(actual_hash, row["artifact_hash"]):
                raise AretError("Intégrité d’artefact pipeline échouée")
        returned = data[:max_bytes]
        return {
            "pipeline_address": make_address("pipeline", pipeline_run_id), "artifact_path": row["artifact_path"],
            "artifact_hash": actual_hash, "artifact_size": len(data), "returned_bytes": len(returned),
            "truncated": len(returned) < len(data), "content": returned.decode("utf-8", errors="replace"),
        }

    def read_artifact(self, proof_id: str, max_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, Any]:
        if max_bytes < 1 or max_bytes > HARD_MAX_BYTES:
            raise AretError(f"max_bytes doit être compris entre 1 et {HARD_MAX_BYTES}")
        with self._read_connection() as conn:
            row = conn.execute("SELECT artifact_path, artifact_hash, artifact_size FROM proof WHERE id=?", (proof_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"Preuve introuvable : {proof_id}")
            if not row["artifact_path"]:
                raise NotFoundError(f"La preuve {proof_id} ne référence aucun artefact")
            file_path = (self.artifacts_dir / row["artifact_path"]).resolve()
            if self.artifacts_dir not in file_path.parents or not file_path.is_file():
                raise AretError("Référence d’artefact hors périmètre ou absente")
            data = file_path.read_bytes()
            actual_hash = hashlib.sha256(data).hexdigest()
            if not hmac.compare_digest(actual_hash, row["artifact_hash"]):
                raise AretError("Intégrité d’artefact échouée : le hash ne correspond plus")
            returned = data[:max_bytes]
        return {
            "proof_address": make_address("proof", proof_id), "artifact_path": row["artifact_path"],
            "artifact_hash": actual_hash, "artifact_size": len(data), "returned_bytes": len(returned),
            "truncated": len(returned) < len(data), "content": returned.decode("utf-8", errors="replace"),
        }

    def _rebuild_fts(self, conn: sqlite3.Connection) -> int:
        conn.execute("DELETE FROM knowledge_fts")
        rows = conn.execute(
            """SELECT k.id, k.title, k.content, COALESCE(group_concat(kt.tag, ' '), '') AS tags
               FROM knowledge k LEFT JOIN knowledge_tag kt ON kt.knowledge_id=k.id GROUP BY k.id"""
        ).fetchall()
        conn.executemany(
            "INSERT INTO knowledge_fts(knowledge_id,title,content,tags) VALUES(?,?,?,?)",
            [(row["id"], row["title"], row["content"], row["tags"]) for row in rows],
        )
        return len(rows)

    def rebuild_index(self, actor: str = "aret-cli") -> dict[str, Any]:
        self._require_write()
        with self._transaction() as conn:
            count = self._rebuild_fts(conn)
            self._audit(conn, actor=actor, operation="REBUILD_FTS", entity_type="index", entity_id="knowledge_fts", after={"indexed_items": count})
        return {"indexed_items": count, "index": "knowledge_fts", "reconstructible_from": "knowledge + knowledge_tag"}

    def _logical_snapshot(self, conn: sqlite3.Connection) -> dict[str, Any]:
        snapshot: dict[str, Any] = {}
        for table in ("component", "function_symbol", "brick", "knowledge", "knowledge_tag", "proof", "proof_link", "relation", "front_state", "audit_event", "migration_batch", "knowledge_source", "id_sequence"):
            snapshot[table] = [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1")]
        snapshot["metadata"] = self._metadata(conn)
        return snapshot

    def _bundle_artifacts(self) -> list[dict[str, Any]]:
        inventory: list[dict[str, Any]] = []
        for artifact in sorted(self.artifacts_dir.rglob("*")):
            if not artifact.is_file():
                continue
            relative = artifact.relative_to(self.artifacts_dir).as_posix()
            data = artifact.read_bytes()
            inventory.append({"path": relative, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})
        return inventory

    @staticmethod
    def _bundle_migrations() -> list[dict[str, str]]:
        schema_dir = Path(__file__).resolve().parents[1] / "schema"
        inventory: list[dict[str, str]] = []
        for migration in sorted(schema_dir.glob("*.sql")):
            data = migration.read_bytes()
            inventory.append({"name": migration.name, "sha256": hashlib.sha256(data).hexdigest()})
        return inventory

    @staticmethod
    def _safe_relative_path(value: str) -> Path:
        candidate = Path(str(value))
        if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
            raise AretError("Chemin de bundle non autorisé")
        return candidate

    def export_bundle(self, output_name: str | None = None) -> dict[str, Any]:
        checkpoint = self.checkpoint_wal()
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        base = re.sub(r"[^A-Za-z0-9_.-]", "_", output_name or f"aret_memory_{stamp}")
        with self._read_connection() as conn:
            snapshot = self._logical_snapshot(conn)
        snapshot_text = canonical_json(snapshot)
        db_hash = sha256_text(snapshot_text)
        migrations = self._bundle_migrations()
        manifest_core = {
            "bundle_version": 3,
            "memory_format_version": snapshot["metadata"].get("memory_format_version", "1"),
            "schema_version": snapshot["metadata"].get("memory_format_version", "1"),
            "created_at": utc_now(),
            "source_device_id": os.environ.get("ARET_SOURCE_DEVICE_ID", "UNSPECIFIED"),
            "db_hash": db_hash,
            "snapshot_sha256": hashlib.sha256(snapshot_text.encode("utf-8")).hexdigest(),
            "artifact_inventory": self._bundle_artifacts(),
            "migrations": migrations,
        }
        manifest = {**manifest_core, "manifest_hash": sha256_text(canonical_json(manifest_core))}
        path = self.exports_dir / f"{base}.bundle.zip"
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            archive.writestr("manifest.json", canonical_json(manifest) + "\n")
            archive.writestr("snapshot.json", snapshot_text + "\n")
            for item in manifest["artifact_inventory"]:
                archive.write(self.artifacts_dir / item["path"], f"artifacts/{item['path']}")
            schema_dir = Path(__file__).resolve().parents[1] / "schema"
            for item in migrations:
                archive.write(schema_dir / item["name"], f"schema/{item['name']}")
        return {"format": "bundle", "path": str(path), "logical_db_hash": db_hash,
                "bundle_hash": manifest["manifest_hash"], "artifact_count": len(manifest["artifact_inventory"]),
                "wal_checkpoint": checkpoint}

    def _read_bundle(self, bundle_path: str | Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, bytes]]:
        source = Path(bundle_path).expanduser().resolve()
        if not source.is_file():
            raise NotFoundError("Bundle introuvable")
        try:
            with zipfile.ZipFile(source, "r") as archive:
                names = set(archive.namelist())
                if "manifest.json" not in names or "snapshot.json" not in names:
                    raise AretError("Bundle incomplet : manifest.json et snapshot.json sont requis")
                if any(name.startswith("/") or ".." in Path(name).parts for name in names):
                    raise AretError("Bundle contient un chemin dangereux")
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                snapshot = json.loads(archive.read("snapshot.json").decode("utf-8"))
                if not isinstance(manifest, dict) or not isinstance(snapshot, dict):
                    raise AretError("Manifest ou snapshot de bundle invalide")
                received_hash = str(manifest.get("manifest_hash", ""))
                core = dict(manifest)
                core.pop("manifest_hash", None)
                if not received_hash or not hmac.compare_digest(received_hash, sha256_text(canonical_json(core))):
                    raise AretError("Hash de manifest de bundle invalide")
                bundle_version = manifest.get("bundle_version")
                if bundle_version not in {2, 3}:
                    raise AretError("Version de bundle non supportée")
                if bundle_version == 3:
                    migrations = manifest.get("migrations")
                    if not isinstance(migrations, list) or not migrations:
                        raise AretError("Inventaire de migrations manquant dans le bundle")
                    seen_migrations: set[str] = set()
                    for item in migrations:
                        if not isinstance(item, dict):
                            raise AretError("Entrée de migration invalide")
                        name = Path(str(item.get("name", ""))).name
                        if name != item.get("name") or not name.endswith(".sql") or name in seen_migrations:
                            raise AretError("Nom de migration invalide")
                        seen_migrations.add(name)
                        member = f"schema/{name}"
                        if member not in names:
                            raise AretError(f"Migration absente du bundle : {name}")
                        if not hmac.compare_digest(hashlib.sha256(archive.read(member)).hexdigest(), str(item.get("sha256", ""))):
                            raise AretError(f"Hash de migration invalide : {name}")
                snapshot_text = canonical_json(snapshot)
                if not hmac.compare_digest(str(manifest.get("db_hash", "")), sha256_text(snapshot_text)):
                    raise AretError("Hash logique du snapshot invalide")
                if not hmac.compare_digest(str(manifest.get("snapshot_sha256", "")), hashlib.sha256(snapshot_text.encode("utf-8")).hexdigest()):
                    raise AretError("Hash binaire du snapshot invalide")
                artifacts: dict[str, bytes] = {}
                inventory = manifest.get("artifact_inventory", [])
                if not isinstance(inventory, list):
                    raise AretError("Inventaire d’artefacts invalide")
                seen: set[str] = set()
                for item in inventory:
                    if not isinstance(item, dict):
                        raise AretError("Entrée d’artefact invalide")
                    relative = self._safe_relative_path(str(item.get("path", ""))).as_posix()
                    if relative in seen:
                        raise AretError("Artefact dupliqué dans le bundle")
                    seen.add(relative)
                    member = f"artifacts/{relative}"
                    if member not in names:
                        raise AretError(f"Artefact manquant dans le bundle : {relative}")
                    data = archive.read(member)
                    if len(data) != int(item.get("size", -1)):
                        raise AretError(f"Taille d’artefact invalide : {relative}")
                    if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), str(item.get("sha256", ""))):
                        raise AretError(f"Hash d’artefact invalide : {relative}")
                    artifacts[relative] = data
        except zipfile.BadZipFile as exc:
            raise AretError("Archive ZIP de bundle invalide") from exc
        return manifest, snapshot, artifacts

    def import_bundle(self, bundle_path: str | Path, actor: str = "aret-bundle-import") -> dict[str, Any]:
        self._require_write()
        manifest, snapshot, artifacts = self._read_bundle(bundle_path)
        bundle_hash = str(manifest["manifest_hash"])
        with self._read_connection() as conn:
            if conn.execute("SELECT 1 FROM bundle_import WHERE bundle_hash=?", (bundle_hash,)).fetchone():
                return {"imported": False, "idempotent": True, "bundle_hash": bundle_hash, "logical_db_hash": manifest["db_hash"]}
            non_empty = any(conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() for table in ("component", "function_symbol", "brick", "knowledge", "proof", "relation"))
        if non_empty:
            raise AretError("Import de bundle refusé : la cible n’est pas vide ; aucune fusion implicite n’est autorisée")
        for relative, data in artifacts.items():
            target = (self.artifacts_dir / self._safe_relative_path(relative)).resolve()
            if self.artifacts_dir not in target.parents:
                raise AretError("Artefact hors périmètre")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and not hmac.compare_digest(hashlib.sha256(target.read_bytes()).hexdigest(), hashlib.sha256(data).hexdigest()):
                raise AretError(f"Collision d’artefact : {relative}")
            target.write_bytes(data)
        table_order = ("component", "function_symbol", "brick", "knowledge", "knowledge_tag", "proof", "proof_link", "relation", "front_state", "migration_batch", "knowledge_source", "audit_event", "id_sequence")
        if not isinstance(snapshot.get("metadata"), dict) or any(not isinstance(snapshot.get(table), list) for table in table_order):
            raise AretError("Snapshot de bundle incomplet")
        with self._transaction() as conn:
            for table in table_order:
                allowed = {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})")}
                for row in snapshot[table]:
                    if not isinstance(row, dict) or not row or not set(row).issubset(allowed):
                        raise AretError(f"Ligne de snapshot invalide pour {table}")
                    if table == "id_sequence":
                        conn.execute(
                            """INSERT INTO id_sequence(entity,next_value) VALUES(?,?)
                               ON CONFLICT(entity) DO UPDATE SET next_value=MAX(id_sequence.next_value, excluded.next_value)""",
                            (row["entity"], row["next_value"]),
                        )
                        continue
                    columns = sorted(row)
                    conn.execute(f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})", [row[column] for column in columns])
            for key, value in snapshot["metadata"].items():
                conn.execute("INSERT INTO store_metadata(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (key, str(value), utc_now()))
            self._rebuild_fts(conn)
            imported = {"bundle_hash": bundle_hash, "source_db_hash": manifest["db_hash"], "manifest_json": canonical_json(manifest), "imported_at": utc_now(), "imported_by": actor}
            conn.execute("INSERT INTO bundle_import(bundle_hash,source_db_hash,manifest_json,imported_at,imported_by) VALUES(:bundle_hash,:source_db_hash,:manifest_json,:imported_at,:imported_by)", imported)
            self._audit(conn, actor=actor, operation="IMPORT_BUNDLE", entity_type="bundle", entity_id=bundle_hash, after={"source_db_hash": manifest["db_hash"], "artifact_count": len(artifacts)})
        return {"imported": True, "idempotent": False, "bundle_hash": bundle_hash, "logical_db_hash": manifest["db_hash"], "artifact_count": len(artifacts)}

    def get_roadmap(
        self,
        milestone: str | None = None,
        component_id: str | None = None,
        target_platform: str | None = None,
        include_done: bool = False,
        max_items: int = 50,
    ) -> dict[str, Any]:
        """Construit une vue compacte, déterministe et bornée du portefeuille de briques actif."""
        if max_items < 1 or max_items > HARD_MAX_ITEMS:
            raise AretError(f"max_items doit être compris entre 1 et {HARD_MAX_ITEMS}")
        milestone = self._normalize_roadmap_value(milestone, "milestone")
        target_platform = self._normalize_roadmap_value(target_platform, "target_platform")
        if component_id:
            component_id = self._validate_identifier(component_id, "Identifiant de composant")
        clauses: list[str] = []
        args: list[Any] = []
        if milestone:
            clauses.append("b.milestone=?")
            args.append(milestone)
        if component_id:
            clauses.append("b.component_id=?")
            args.append(component_id)
        if target_platform:
            clauses.append("b.target_platform=?")
            args.append(target_platform)
        if not include_done:
            clauses.append("b.state <> 'DONE'")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        order = " ORDER BY b.priority ASC, CASE b.state WHEN 'ACTIVE' THEN 0 WHEN 'BLOCKED' THEN 1 WHEN 'PLANNED' THEN 2 WHEN 'DONE' THEN 3 ELSE 4 END, b.id ASC"
        with self._read_connection() as conn:
            rows = conn.execute(
                "SELECT b.* FROM brick b" + where + order + " LIMIT ?", [*args, max_items + 1]
            ).fetchall()
            truncated = len(rows) > max_items
            selected = rows[:max_items]
            bricks: list[dict[str, Any]] = []
            for row in selected:
                brick = dict(row)
                relations = [dict(item) for item in conn.execute(
                    """SELECT * FROM relation WHERE status='ACTIVE' AND (from_id=? OR to_id=?)
                       ORDER BY relation_type, created_at, id""", (brick["id"], brick["id"])
                ).fetchall()]
                related: list[dict[str, str]] = []
                for relation in relations:
                    other_id = relation["to_id"] if relation["from_id"] == brick["id"] else relation["from_id"]
                    related.append({
                        "relation_id": relation["id"], "relation_type": relation["relation_type"],
                        "entity_id": other_id, "address": self._entity_address(conn, other_id),
                    })
                brick["address"] = make_address("brick", brick["id"])
                brick["blockers"] = [item for item in related if item["relation_type"] == "BLOCKED_BY"]
                brick["implements"] = [item for item in related if item["relation_type"] == "IMPLEMENTS"]
                brick["informed_by"] = [item for item in related if item["relation_type"] == "INFORMED_BY"]
                brick["evidence"] = [item for item in related if item["relation_type"] == "VERIFIED_BY"]
                brick["relations"] = related
                bricks.append(brick)
        summary = {state.lower(): sum(1 for brick in bricks if brick["state"] == state) for state in sorted(BRICK_STATES)}
        filters = {
            "milestone": milestone, "component_id": component_id, "target_platform": target_platform,
            "include_done": include_done, "max_items": max_items,
        }
        logical_view_hash = sha256_text(canonical_json({"filters": filters, "bricks": bricks, "truncated": truncated}))
        notice = "Résultats tronqués : réduisez les filtres ou utilisez un max_items plus élevé." if truncated else None
        return {
            "filters": filters, "summary": summary, "bricks": bricks, "truncated": truncated,
            "notice": notice, "logical_view_hash": logical_view_hash,
        }

    def export_roadmap(
        self,
        milestone: str | None = None,
        component_id: str | None = None,
        target_platform: str | None = None,
        include_done: bool = False,
        max_items: int = 50,
        output_name: str | None = None,
    ) -> dict[str, Any]:
        """Exporte une roadmap Markdown dérivée, jamais une seconde source de vérité modifiable."""
        roadmap = self.get_roadmap(milestone, component_id, target_platform, include_done, max_items)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        base = re.sub(r"[^A-Za-z0-9_.-]", "_", output_name or f"aret_roadmap_{stamp}")
        filters = roadmap["filters"]
        lines = [
            "# ARET — Roadmap reconstruite", "",
            "Cette vue est dérivée du Memory Store SQLite canonique ; elle ne doit pas être éditée comme source de vérité.",
            f"Hash logique de la vue : `{roadmap['logical_view_hash']}`", "",
            "## Filtres", "",
            f"- Jalon : `{filters['milestone'] or 'tous'}`",
            f"- Composant : `{filters['component_id'] or 'tous'}`",
            f"- Plateforme : `{filters['target_platform'] or 'toutes'}`",
            f"- Briques terminées incluses : `{str(filters['include_done']).lower()}`", "",
            "## Synthèse", "",
        ]
        for state, count in roadmap["summary"].items():
            lines.append(f"- `{state.upper()}` : {count}")
        lines.extend(["", "## Briques", ""])
        if not roadmap["bricks"]:
            lines.append("_Aucune brique ne correspond aux filtres._")
        for brick in roadmap["bricks"]:
            lines.extend([
                f"### {brick['id']} — {brick['title']}", "",
                f"- Adresse : `{brick['address']}`",
                f"- État : `{brick['state']}`",
                f"- Priorité : `{brick['priority']}`",
                f"- Jalon : `{brick['milestone'] or 'non classé'}`",
                f"- Plateforme : `{brick['target_platform'] or 'transverse'}`",
                f"- Composant : `{brick['component_id'] or 'transverse'}`",
            ])
            for label, values in (("Bloqueurs", brick["blockers"]), ("Implémente", brick["implements"]), ("Informée par", brick["informed_by"]), ("Preuves", brick["evidence"])):
                if values:
                    lines.append(f"- {label} : " + ", ".join(f"`{item['address']}`" for item in values))
            lines.extend(["", brick["description"], ""])
        if roadmap["truncated"]:
            lines.extend(["## Avertissement", "", roadmap["notice"] or "Résultats tronqués.", ""])
        path = self.exports_dir / f"{base}.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        return {"format": "roadmap", "path": str(path), "logical_view_hash": roadmap["logical_view_hash"], "brick_count": len(roadmap["bricks"]), "truncated": roadmap["truncated"]}

    def export_reference_91(self, output_name: str | None = None) -> dict[str, Any]:
        """Reconstruit la référence 91 depuis STATE, RULE, MEASUREMENT, BRICK et DECISION canoniques."""
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        base = re.sub(r"[^A-Za-z0-9_.-]", "_", output_name or f"aret_reference_91_{stamp}")
        with self._read_connection() as conn:
            rows = conn.execute(
                """SELECT id,type,status,title,content,content_hash,updated_at FROM knowledge
                   WHERE type IN ('STATE','RULE','MEASUREMENT','DECISION')
                   ORDER BY type, updated_at DESC, id"""
            ).fetchall()
            bricks = conn.execute("SELECT id,component_id,title,state,description,created_at FROM brick ORDER BY state,id").fetchall()
            snapshot_hash = sha256_text(canonical_json({"knowledge": [dict(row) for row in rows], "bricks": [dict(row) for row in bricks]}))
        lines = ["# 91 — Référence ARET reconstruite", "", "Cette vue est dérivée du Memory Store SQLite canonique.",
                 f"Hash logique de la vue : `{snapshot_hash}`", ""]
        for knowledge_type in ("STATE", "RULE", "MEASUREMENT", "DECISION"):
            lines.extend([f"## {knowledge_type}", ""])
            typed = [row for row in rows if row["type"] == knowledge_type]
            if not typed:
                lines.append("_Aucun objet canonique._\n")
                continue
            for row in typed:
                lines.extend([f"### {row['id']} — {row['title']}", "", f"- Statut : `{row['status']}`", f"- Hash : `{row['content_hash']}`", "", row["content"], ""])
        lines.extend(["## BRICK", ""])
        if not bricks:
            lines.append("_Aucune brique canonique._")
        for brick in bricks:
            lines.extend([f"### {brick['id']} — {brick['title']}", "", f"- Composant : `{brick['component_id']}`", f"- État : `{brick['state']}`", "", brick["description"], ""])
        path = self.exports_dir / f"{base}.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        return {"format": "reference_91", "path": str(path), "logical_view_hash": snapshot_hash,
                "knowledge_count": len(rows), "brick_count": len(bricks)}

    def export(self, export_format: str = "json", output_name: str | None = None) -> dict[str, Any]:
        export_format = export_format.lower()
        if export_format not in {"json", "markdown", "html", "bundle"}:
            raise AretError("Format d’export pris en charge : json, markdown, html ou bundle")
        if export_format == "bundle":
            return self.export_bundle(output_name)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        base = re.sub(r"[^A-Za-z0-9_.-]", "_", output_name or f"aret_memory_{stamp}")
        with self._read_connection() as conn:
            snapshot = self._logical_snapshot(conn)
            db_hash = sha256_text(canonical_json(snapshot))
        if export_format == "json":
            path = self.exports_dir / f"{base}.json"
            path.write_text(json.dumps({"db_hash": db_hash, "snapshot": snapshot}, ensure_ascii=False, indent=2), encoding="utf-8")
        elif export_format == "markdown":
            path = self.exports_dir / f"{base}.md"
            lines = ["# ARET-MMU — Export dérivé", "", f"Hash logique : `{db_hash}`", "", "## Active Front", ""]
            for item in snapshot["front_state"]:
                lines.append(f"- **{item['key']}** : {item['value']}")
            lines.extend(["", "## Connaissances", ""])
            for item in snapshot["knowledge"]:
                lines.extend([f"### {item['id']} — {item['title']}", "", f"- Type : `{item['type']}`", f"- Statut : `{item['status']}`", f"- Hash : `{item['content_hash']}`", "", item["content"], ""])
            path.write_text("\n".join(lines), encoding="utf-8")
        else:
            path = self.exports_dir / f"{base}.html"
            front_rows = "".join(
                f"<tr><th>{html.escape(str(item['key']))}</th><td>{html.escape(str(item['value']))}</td></tr>"
                for item in snapshot["front_state"]
            ) or "<tr><td colspan='2'><em>Front vide</em></td></tr>"
            knowledge_rows = "".join(
                "<article><h3 id='{id}'>{id} — {title}</h3><dl>"
                "<dt>Type</dt><dd>{typ}</dd><dt>Statut</dt><dd>{status}</dd><dt>Hash</dt><dd><code>{digest}</code></dd>"
                "</dl><pre>{content}</pre></article>".format(
                    id=html.escape(str(item["id"])), title=html.escape(str(item["title"])),
                    typ=html.escape(str(item["type"])), status=html.escape(str(item["status"])),
                    digest=html.escape(str(item["content_hash"])), content=html.escape(str(item["content"])),
                ) for item in snapshot["knowledge"]
            ) or "<p><em>Aucune connaissance.</em></p>"
            page = f"""<!doctype html>
<html lang=\"fr\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>ARET-MMU — Export dérivé</title><style>
body{{font-family:system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#18212b}} h1,h2,h3{{color:#143a5d}} table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #cbd5df;padding:.5rem;text-align:left}}th{{background:#eef4f8}}article{{border-top:1px solid #cbd5df;padding:1rem 0}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f8fa;padding:1rem;border-radius:5px}}code{{overflow-wrap:anywhere}}
</style></head><body><h1>ARET-MMU — Export dérivé</h1><p>Hash logique canonique : <code>{html.escape(db_hash)}</code></p>
<h2>Active Front</h2><table><tbody>{front_rows}</tbody></table><h2>Connaissances</h2>{knowledge_rows}
<footer><p>Vue dérivée : SQLite reste la source canonique.</p></footer></body></html>"""
            path.write_text(page, encoding="utf-8")
        return {"format": export_format, "path": str(path), "logical_db_hash": db_hash}

    def audit_events(self, limit: int = 100) -> list[dict[str, Any]]:
        if limit < 1 or limit > 1000:
            raise AretError("La limite d’audit doit être comprise entre 1 et 1000")
        with self._read_connection() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM audit_event ORDER BY timestamp DESC, id DESC LIMIT ?", (limit,))]
