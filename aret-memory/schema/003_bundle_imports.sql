PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS bundle_import (
    bundle_hash TEXT PRIMARY KEY,
    source_db_hash TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    imported_by TEXT NOT NULL
) STRICT;
