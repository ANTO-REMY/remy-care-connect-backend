-- 027_prevent_duplicate_active_checkin_escalations.sql
-- Prevent multiple active escalations for the same check-in.

CREATE UNIQUE INDEX IF NOT EXISTS uq_escalations_active_checkin
  ON escalations(checkin_id)
  WHERE checkin_id IS NOT NULL
    AND status IN ('pending', 'in_progress');
