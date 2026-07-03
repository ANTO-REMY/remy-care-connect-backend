-- Migration 049: Persist saved Nairobi administrative location fields on health_facilities
-- Purpose: Support one-time point-in-polygon enrichment and fast claim filtering

ALTER TABLE health_facilities
ADD COLUMN IF NOT EXISTS subcounty_name VARCHAR(128),
ADD COLUMN IF NOT EXISTS ward_name VARCHAR(128),
ADD COLUMN IF NOT EXISTS location_match_status VARCHAR(32) NOT NULL DEFAULT 'manual_review',
ADD COLUMN IF NOT EXISTS location_match_method VARCHAR(64),
ADD COLUMN IF NOT EXISTS location_matched_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_hf_saved_subcounty_name ON health_facilities(subcounty_name);
CREATE INDEX IF NOT EXISTS idx_hf_saved_ward_name ON health_facilities(ward_name);
CREATE INDEX IF NOT EXISTS idx_hf_location_match_status ON health_facilities(location_match_status);

CREATE INDEX IF NOT EXISTS idx_hf_claim_scope_unclaimed ON health_facilities(subcounty_name, ward_name)
WHERE facility_admin_id IS NULL;

COMMENT ON COLUMN health_facilities.subcounty_name IS 'Saved sub-county name computed from one-time boundary enrichment';
COMMENT ON COLUMN health_facilities.ward_name IS 'Saved ward name computed from one-time boundary enrichment';
COMMENT ON COLUMN health_facilities.location_match_status IS 'Outcome of local coordinate-to-boundary enrichment';
COMMENT ON COLUMN health_facilities.location_match_method IS 'Method used to assign administrative location';
COMMENT ON COLUMN health_facilities.location_matched_at IS 'UTC timestamp when administrative location was last computed';
