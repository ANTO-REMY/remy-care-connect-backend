-- 033_create_weight_log.sql
-- Stores weekly weight entries from mothers

CREATE TABLE IF NOT EXISTS weight_log (
    id SERIAL PRIMARY KEY,
    mother_id INTEGER NOT NULL REFERENCES mothers(id) ON DELETE CASCADE,
    weight_kg NUMERIC(5,2) NOT NULL,
    week_number INTEGER,
    notes TEXT,
    recorded_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_weight_log_mother ON weight_log(mother_id);
