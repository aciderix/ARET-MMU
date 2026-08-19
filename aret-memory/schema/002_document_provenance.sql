PRAGMA foreign_keys = ON;

ALTER TABLE knowledge ADD COLUMN effective_at TEXT;

CREATE TABLE IF NOT EXISTS migration_batch (
    id TEXT PRIMARY KEY,
    source_repository TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    importer_version TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    source_manifest_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED', 'DRY_RUN')),
    summary_json TEXT NOT NULL DEFAULT '{}'
) STRICT;

CREATE TABLE IF NOT EXISTS knowledge_source (
    id TEXT PRIMARY KEY,
    knowledge_id TEXT NOT NULL REFERENCES knowledge(id) ON DELETE RESTRICT,
    source_repository TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_start_line INTEGER NOT NULL CHECK (source_start_line > 0),
    source_end_line INTEGER NOT NULL CHECK (source_end_line >= source_start_line),
    source_section TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    imported_by TEXT NOT NULL,
    migration_batch_id TEXT REFERENCES migration_batch(id),
    UNIQUE(knowledge_id, source_revision, source_path, source_start_line, source_end_line)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_knowledge_source_lookup
ON knowledge_source(source_path, source_start_line, source_end_line);

CREATE INDEX IF NOT EXISTS idx_knowledge_source_knowledge
ON knowledge_source(knowledge_id);
