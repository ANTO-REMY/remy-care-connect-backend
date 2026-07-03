-- Migration 042: Add optional linked referral facility to CHW profiles

ALTER TABLE chws
ADD COLUMN IF NOT EXISTS linked_facility_id BIGINT REFERENCES health_facilities(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_chws_linked_facility_id ON chws(linked_facility_id);
