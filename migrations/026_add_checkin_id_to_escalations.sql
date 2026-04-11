-- 026_add_checkin_id_to_escalations.sql
-- Link escalations to a specific daily check-in event (optional)

ALTER TABLE escalations
  ADD COLUMN IF NOT EXISTS checkin_id INTEGER REFERENCES daily_checkin(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_escalations_checkin_id
  ON escalations(checkin_id);
