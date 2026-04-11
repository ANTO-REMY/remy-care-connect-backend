-- 032_add_symptoms_to_daily_checkin.sql
-- Adds a JSONB symptoms array to daily_checkin for structured symptom tracking

ALTER TABLE daily_checkin
  ADD COLUMN IF NOT EXISTS symptoms JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN daily_checkin.symptoms IS
  'Array of symptom strings selected by the mother, e.g. ["headache","nausea"]';
