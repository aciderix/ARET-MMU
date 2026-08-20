-- Assets externes et exécutions de pipelines ARET-MMU.
-- Les scripts restent dans une liste fermée côté adaptateur ; SQLite conserve
-- uniquement l’identité, la provenance, les paramètres, les artefacts et l’audit.

CREATE TABLE IF NOT EXISTS asset (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('PE32','DLL','SNAPSHOT','IAT_MAP','CORPUS','GENERATED','TOOLCHAIN_REPORT')),
    source_kind TEXT NOT NULL CHECK(source_kind IN ('LOCAL','NETWORK','GENERATED','SNAPSHOT')),
    relative_path TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
    provenance_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL
) STRICT;

CREATE INDEX IF NOT EXISTS idx_asset_kind_created ON asset(kind, created_at DESC, id);

CREATE TABLE IF NOT EXISTS pipeline_run (
    id TEXT PRIMARY KEY,
    pipeline_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    policy TEXT NOT NULL CHECK(policy IN ('READ_ONLY','GENERATE','NETWORK','SENSITIVE')),
    result TEXT NOT NULL CHECK(result IN ('PASS','FAIL','ERROR','SKIPPED','UNKNOWN','PLANNED')),
    command TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    artifact_path TEXT NOT NULL DEFAULT '',
    artifact_hash TEXT NOT NULL DEFAULT '',
    exit_code INTEGER,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL
) STRICT;

CREATE INDEX IF NOT EXISTS idx_pipeline_run_name_created ON pipeline_run(pipeline_name, created_at DESC, id);
CREATE INDEX IF NOT EXISTS idx_pipeline_run_result_created ON pipeline_run(result, created_at DESC, id);

INSERT OR IGNORE INTO id_sequence(entity, next_value) VALUES ('asset', 1);
INSERT OR IGNORE INTO id_sequence(entity, next_value) VALUES ('pipeline_run', 1);
