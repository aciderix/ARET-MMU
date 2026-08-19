PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,
    checksum TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS store_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS id_sequence (
    entity TEXT PRIMARY KEY,
    next_value INTEGER NOT NULL CHECK (next_value > 0)
) STRICT;

CREATE TABLE IF NOT EXISTS component (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS function_symbol (
    id TEXT PRIMARY KEY,
    component_id TEXT NOT NULL REFERENCES component(id),
    module TEXT NOT NULL DEFAULT '',
    symbol TEXT NOT NULL,
    calling_convention TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    UNIQUE(component_id, module, symbol)
) STRICT;

CREATE TABLE IF NOT EXISTS brick (
    id TEXT PRIMARY KEY,
    component_id TEXT REFERENCES component(id),
    title TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('PLANNED', 'ACTIVE', 'BLOCKED', 'DONE', 'OBSOLETE')),
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS knowledge (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN (
        'RULE', 'ARCHITECTURE', 'DECISION', 'FORENSIC', 'OBSERVATION',
        'HYPOTHESIS', 'STATE', 'MEASUREMENT', 'DISCOVERY'
    )),
    status TEXT NOT NULL CHECK (status IN (
        'ACTIVE', 'PROVEN', 'OBSERVED', 'HYPOTHESIS', 'SUPERSEDED',
        'OBSOLETE', 'CONFLICTING'
    )),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    component_id TEXT REFERENCES component(id),
    function_id TEXT REFERENCES function_symbol(id),
    brick_id TEXT REFERENCES brick(id),
    supersedes_id TEXT REFERENCES knowledge(id),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS knowledge_tag (
    knowledge_id TEXT NOT NULL REFERENCES knowledge(id) ON DELETE RESTRICT,
    tag TEXT NOT NULL,
    PRIMARY KEY (knowledge_id, tag),
    CHECK (length(tag) BETWEEN 1 AND 64)
) STRICT;

CREATE TABLE IF NOT EXISTS proof (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    command TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL CHECK (result IN ('PASS', 'FAIL', 'ERROR', 'SKIPPED', 'UNKNOWN')),
    exit_code INTEGER,
    stdout_ref TEXT NOT NULL DEFAULT '',
    stderr_ref TEXT NOT NULL DEFAULT '',
    artifact_path TEXT NOT NULL DEFAULT '',
    artifact_hash TEXT NOT NULL DEFAULT '',
    artifact_size INTEGER NOT NULL DEFAULT 0 CHECK (artifact_size >= 0),
    environment_json TEXT NOT NULL DEFAULT '{}',
    started_at TEXT,
    finished_at TEXT,
    payload_hash TEXT NOT NULL,
    receipt_hmac TEXT NOT NULL DEFAULT '',
    admissible INTEGER NOT NULL DEFAULT 0 CHECK (admissible IN (0, 1)),
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS proof_link (
    knowledge_id TEXT NOT NULL REFERENCES knowledge(id) ON DELETE RESTRICT,
    proof_id TEXT NOT NULL REFERENCES proof(id) ON DELETE RESTRICT,
    linked_at TEXT NOT NULL,
    linked_by TEXT NOT NULL,
    PRIMARY KEY (knowledge_id, proof_id)
) STRICT;

CREATE TABLE IF NOT EXISTS relation (
    id TEXT PRIMARY KEY,
    from_id TEXT NOT NULL,
    relation_type TEXT NOT NULL CHECK (relation_type IN (
        'VERIFIED_BY', 'SUPERSEDES', 'INFORMED_BY', 'BLOCKED_BY', 'IMPLEMENTS',
        'DERIVED_FROM', 'CONCERNS', 'APPLIES_TO', 'CAUSED_BY', 'EVOLVES_TO'
    )),
    to_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    UNIQUE(from_id, relation_type, to_id)
) STRICT;

CREATE TABLE IF NOT EXISTS front_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS audit_event (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL,
    operation TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    payload_before TEXT,
    payload_after TEXT
) STRICT;

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
    knowledge_id UNINDEXED,
    title,
    content,
    tags,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE INDEX IF NOT EXISTS idx_knowledge_component ON knowledge(component_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_function ON knowledge(function_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_brick ON knowledge(brick_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_type_status ON knowledge(type, status);
CREATE INDEX IF NOT EXISTS idx_knowledge_created_at ON knowledge(created_at);
CREATE INDEX IF NOT EXISTS idx_proof_result_admissible ON proof(result, admissible);
CREATE INDEX IF NOT EXISTS idx_proof_link_knowledge ON proof_link(knowledge_id);
CREATE INDEX IF NOT EXISTS idx_relation_from_type ON relation(from_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_relation_to_type ON relation(to_id, relation_type);

CREATE TRIGGER IF NOT EXISTS reject_unproven_insert
BEFORE INSERT ON knowledge
WHEN NEW.status = 'PROVEN'
BEGIN
    SELECT RAISE(ABORT, 'PROVEN requires an already linked admissible PASS proof');
END;

CREATE TRIGGER IF NOT EXISTS reject_unproven_promotion
BEFORE UPDATE OF status ON knowledge
WHEN NEW.status = 'PROVEN'
AND NOT EXISTS (
    SELECT 1
    FROM proof_link AS link
    JOIN proof AS p ON p.id = link.proof_id
    WHERE link.knowledge_id = NEW.id
      AND p.result = 'PASS'
      AND p.admissible = 1
)
BEGIN
    SELECT RAISE(ABORT, 'PROVEN requires a linked admissible PASS proof');
END;

CREATE TRIGGER IF NOT EXISTS reject_knowledge_content_rewrite
BEFORE UPDATE ON knowledge
WHEN NEW.type <> OLD.type
  OR NEW.title <> OLD.title
  OR NEW.content <> OLD.content
  OR NEW.component_id IS NOT OLD.component_id
  OR NEW.function_id IS NOT OLD.function_id
  OR NEW.brick_id IS NOT OLD.brick_id
  OR NEW.supersedes_id IS NOT OLD.supersedes_id
  OR NEW.version <> OLD.version
  OR NEW.content_hash <> OLD.content_hash
  OR NEW.created_at <> OLD.created_at
  OR NEW.created_by <> OLD.created_by
BEGIN
    SELECT RAISE(ABORT, 'knowledge is append-only; create a new version instead');
END;

INSERT OR IGNORE INTO id_sequence(entity, next_value) VALUES
    ('knowledge', 1),
    ('proof', 1),
    ('relation', 1),
    ('audit', 1);
