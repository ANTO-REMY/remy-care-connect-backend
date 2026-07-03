-- Migration 048: Add Nairobi scope flags to health_facilities
-- Purpose: Separate Nairobi facilities from non-Nairobi facilities to reduce query noise

ALTER TABLE health_facilities
ADD COLUMN IF NOT EXISTS is_in_nairobi BOOLEAN NOT NULL DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS nairobi_scope_source VARCHAR(32) NOT NULL DEFAULT 'unset',
ADD COLUMN IF NOT EXISTS near_nairobi_boundary BOOLEAN NOT NULL DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS nairobi_boundary_distance_m DOUBLE PRECISION;

CREATE INDEX IF NOT EXISTS idx_hf_is_in_nairobi ON health_facilities(is_in_nairobi);
CREATE INDEX IF NOT EXISTS idx_hf_near_nairobi_boundary ON health_facilities(near_nairobi_boundary);

-- Partial index to speed common "Nairobi only" lookups
CREATE INDEX IF NOT EXISTS idx_hf_nairobi_subset ON health_facilities(id)
WHERE is_in_nairobi = TRUE;

COMMENT ON COLUMN health_facilities.is_in_nairobi IS 'True when facility is inside Nairobi County boundary';
COMMENT ON COLUMN health_facilities.nairobi_scope_source IS 'How Nairobi scope was assigned (e.g. geojson_polygon_filter_v1)';
COMMENT ON COLUMN health_facilities.near_nairobi_boundary IS 'True when facility is near Nairobi boundary (manual review threshold)';
COMMENT ON COLUMN health_facilities.nairobi_boundary_distance_m IS 'Approximate distance in meters from point to Nairobi boundary';