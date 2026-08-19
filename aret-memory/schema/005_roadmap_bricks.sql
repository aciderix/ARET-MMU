-- Métadonnées de portfolio V1.1 pour les briques ARET.
-- Ces colonnes classent les chantiers sans transformer les descriptions ou les connaissances
-- en une seconde source de vérité de roadmap.
ALTER TABLE brick ADD COLUMN milestone TEXT;
ALTER TABLE brick ADD COLUMN target_platform TEXT;
ALTER TABLE brick ADD COLUMN priority INTEGER NOT NULL DEFAULT 3
    CHECK (priority BETWEEN 1 AND 5);

CREATE INDEX IF NOT EXISTS idx_brick_roadmap
    ON brick(milestone, target_platform, priority, state, component_id, id);
