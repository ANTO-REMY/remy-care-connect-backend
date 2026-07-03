-- Migration 043: Add inferred administrative mapping fields to health_facilities

ALTER TABLE health_facilities
ADD COLUMN IF NOT EXISTS inferred_ward_id BIGINT REFERENCES wards(id) ON DELETE SET NULL,
ADD COLUMN IF NOT EXISTS inferred_sub_county_id BIGINT REFERENCES sub_counties(id) ON DELETE SET NULL,
ADD COLUMN IF NOT EXISTS inference_source VARCHAR(32) NOT NULL DEFAULT 'none',
ADD COLUMN IF NOT EXISTS inference_confidence DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS location_quality_status VARCHAR(16) NOT NULL DEFAULT 'unknown';

CREATE INDEX IF NOT EXISTS idx_hf_inferred_ward_id ON health_facilities(inferred_ward_id);
CREATE INDEX IF NOT EXISTS idx_hf_inferred_sub_county_id ON health_facilities(inferred_sub_county_id);
CREATE INDEX IF NOT EXISTS idx_hf_location_quality_status ON health_facilities(location_quality_status);
