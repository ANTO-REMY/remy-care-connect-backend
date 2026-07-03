-- Migration 045: Add ticketing fields to appointment_schedule
-- Date: 2026-07-01

BEGIN;

ALTER TABLE appointment_schedule
  ADD COLUMN IF NOT EXISTS ticket_code VARCHAR(32),
  ADD COLUMN IF NOT EXISTS ticket_status VARCHAR(16) NOT NULL DEFAULT 'active',
  ADD COLUMN IF NOT EXISTS validated_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS validated_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS validation_method VARCHAR(16),
  ADD COLUMN IF NOT EXISTS ticket_last_event_at TIMESTAMPTZ;

UPDATE appointment_schedule
SET
  ticket_code = CONCAT(
    'RCC-APT-',
    UPPER(SUBSTRING(MD5(CONCAT('appointment_schedule:', id::text, ':', COALESCE(created_at::text, NOW()::text))) FROM 1 FOR 8))
  ),
  ticket_last_event_at = COALESCE(ticket_last_event_at, updated_at, created_at, NOW())
WHERE ticket_code IS NULL;

ALTER TABLE appointment_schedule
  ALTER COLUMN ticket_code SET NOT NULL;

ALTER TABLE appointment_schedule
  DROP CONSTRAINT IF EXISTS chk_appointment_ticket_status;

ALTER TABLE appointment_schedule
  ADD CONSTRAINT chk_appointment_ticket_status
  CHECK (ticket_status IN ('active', 'used', 'canceled', 'expired'));

ALTER TABLE appointment_schedule
  DROP CONSTRAINT IF EXISTS chk_appointment_validation_method;

ALTER TABLE appointment_schedule
  ADD CONSTRAINT chk_appointment_validation_method
  CHECK (validation_method IS NULL OR validation_method IN ('manual', 'qr', 'otp'));

CREATE UNIQUE INDEX IF NOT EXISTS uq_appointment_schedule_ticket_code
  ON appointment_schedule(ticket_code);

CREATE INDEX IF NOT EXISTS idx_appointment_schedule_ticket_status
  ON appointment_schedule(ticket_status);

CREATE INDEX IF NOT EXISTS idx_appointment_schedule_validated_by_user_id
  ON appointment_schedule(validated_by_user_id);

COMMIT;
