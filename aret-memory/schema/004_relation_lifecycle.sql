-- Cycle de vie append-only des relations : une relation remplacée demeure historique,
-- mais la traversée opérationnelle peut cibler exclusivement les liens actifs.
ALTER TABLE relation ADD COLUMN status TEXT NOT NULL DEFAULT 'ACTIVE'
    CHECK (status IN ('ACTIVE', 'SUPERSEDED'));
ALTER TABLE relation ADD COLUMN superseded_by TEXT;

CREATE INDEX IF NOT EXISTS idx_relation_active_from_type
    ON relation(from_id, relation_type, status);
CREATE INDEX IF NOT EXISTS idx_relation_active_to_type
    ON relation(to_id, relation_type, status);
