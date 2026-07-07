-- Migration 051: Create CHW facility submissions table for pending manual review
-- Purpose: Allow CHWs to suggest linked facilities during registration when no existing
--          facility match is found in the selected sub-county.

CREATE TABLE IF NOT EXISTS chw_facility_submissions (
    id SERIAL PRIMARY KEY,
    submitted_by_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chw_id BIGINT REFERENCES chws(id) ON DELETE SET NULL,
    facility_name VARCHAR(255) NOT NULL,
    normalized_facility_name VARCHAR(255) NOT NULL,
    ward_id BIGINT NOT NULL REFERENCES wards(id) ON DELETE RESTRICT,
    sub_county_id BIGINT NOT NULL REFERENCES sub_counties(id) ON DELETE RESTRICT,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    matched_health_facility_id BIGINT REFERENCES health_facilities(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    updated_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chk_chw_facility_submission_status'
  ) THEN
    ALTER TABLE chw_facility_submissions
    ADD CONSTRAINT chk_chw_facility_submission_status
    CHECK (status IN ('pending', 'approved', 'rejected'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_cfs_submitted_by_user ON chw_facility_submissions(submitted_by_user_id);
CREATE INDEX IF NOT EXISTS idx_cfs_chw_id ON chw_facility_submissions(chw_id);
CREATE INDEX IF NOT EXISTS idx_cfs_status ON chw_facility_submissions(status);
CREATE INDEX IF NOT EXISTS idx_cfs_ward_id ON chw_facility_submissions(ward_id);
CREATE INDEX IF NOT EXISTS idx_cfs_sub_county_id ON chw_facility_submissions(sub_county_id);
CREATE INDEX IF NOT EXISTS idx_cfs_matched_facility_id ON chw_facility_submissions(matched_health_facility_id);
CREATE INDEX IF NOT EXISTS idx_cfs_normalized_name ON chw_facility_submissions(normalized_facility_name);
CREATE INDEX IF NOT EXISTS idx_cfs_subcounty_name_status
  ON chw_facility_submissions(sub_county_id, normalized_facility_name, status);

CREATE UNIQUE INDEX IF NOT EXISTS uq_cfs_one_pending_per_chw
  ON chw_facility_submissions(chw_id)
  WHERE chw_id IS NOT NULL AND status = 'pending';

ALTER TABLE chws
ADD COLUMN IF NOT EXISTS pending_facility_submission_id BIGINT REFERENCES chw_facility_submissions(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_chws_pending_facility_submission_id
  ON chws(pending_facility_submission_id);

COMMENT ON TABLE chw_facility_submissions IS 'Pending facility submissions entered by CHWs for manual review';
COMMENT ON COLUMN chw_facility_submissions.normalized_facility_name IS 'Normalized facility name used for duplicate detection within a sub-county';
COMMENT ON COLUMN chw_facility_submissions.matched_health_facility_id IS 'Resolved health_facilities.id after manual approval or duplicate matching';
