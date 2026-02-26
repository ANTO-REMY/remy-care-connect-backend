-- Migration 016: Add sub_county_id FK to mothers, chws, nurses.
-- Stored alongside ward_id for fast location-based matching (e.g. CHW ↔ Mother assignment).
-- sub_county_id is derived from the ward at registration time and stored denormalized.

ALTER TABLE mothers
    ADD COLUMN sub_county_id INTEGER NOT NULL REFERENCES sub_counties(id);

ALTER TABLE chws
    ADD COLUMN sub_county_id INTEGER NOT NULL REFERENCES sub_counties(id);

ALTER TABLE nurses
    ADD COLUMN sub_county_id INTEGER NOT NULL REFERENCES sub_counties(id);

CREATE INDEX IF NOT EXISTS idx_mothers_sub_county_id ON mothers(sub_county_id);
CREATE INDEX IF NOT EXISTS idx_chws_sub_county_id    ON chws(sub_county_id);
CREATE INDEX IF NOT EXISTS idx_nurses_sub_county_id  ON nurses(sub_county_id);
