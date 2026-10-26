-- 004: JSON pipeline artifacts (reports, summaries) so a hosted API without the local
-- data/outputs folder can serve them. Seeded by database/seeds/publish.py.
CREATE TABLE IF NOT EXISTS artifacts (
    name        TEXT PRIMARY KEY,
    body        JSONB NOT NULL,
    run_id      VARCHAR(48),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
