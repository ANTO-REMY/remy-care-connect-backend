-- Migration 015: Add ward_id FK (NOT NULL) to mothers, chws, and nurses.
-- ward_id is required at registration time — no default, no nulls.
-- Also relax the location column to nullable since we derive it from ward name.

ALTER TABLE mothers
    ADD COLUMN ward_id INTEGER NOT NULL REFERENCES wards(id);

ALTER TABLE chws
    ADD COLUMN ward_id INTEGER NOT NULL REFERENCES wards(id);

ALTER TABLE nurses
    ADD COLUMN ward_id INTEGER NOT NULL REFERENCES wards(id);

-- Make the old free-text location column optional (derived from ward name)
ALTER TABLE mothers ALTER COLUMN location DROP NOT NULL;
ALTER TABLE chws    ALTER COLUMN location DROP NOT NULL;
ALTER TABLE nurses  ALTER COLUMN location DROP NOT NULL;

CREATE INDEX IF NOT EXISTS idx_mothers_ward_id ON mothers(ward_id);
CREATE INDEX IF NOT EXISTS idx_chws_ward_id    ON chws(ward_id);
CREATE INDEX IF NOT EXISTS idx_nurses_ward_id  ON nurses(ward_id);
