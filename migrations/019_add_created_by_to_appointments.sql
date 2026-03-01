-- Migration 019: Add created_by_user_id to appointment_schedule
-- Tracks who (mother, CHW, or nurse) created the appointment for proper UI display

ALTER TABLE appointment_schedule
    ADD COLUMN IF NOT EXISTS created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;

-- Index for filtering appointments by creator
CREATE INDEX IF NOT EXISTS idx_appointment_schedule_created_by ON appointment_schedule(created_by_user_id);

-- For existing appointments, try to assign based on logic:
-- If it's a mother → mother (the person requesting the appointment)
-- If it's a CHW → keep NULL (legacy, can't determine)
-- UPDATE appointment_schedule
--   SET created_by_user_id = mother_id
--   WHERE created_by_user_id IS NULL;
