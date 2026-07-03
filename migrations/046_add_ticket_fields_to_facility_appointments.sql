-- Migration 046: Add ticketing fields to facility_appointments
-- Date: 2026-07-01

BEGIN;

ALTER TABLE facility_appointments
  ADD COLUMN IF NOT EXISTS ticket_code VARCHAR(32),
  ADD COLUMN IF NOT EXISTS ticket_status VARCHAR(16) NOT NULL DEFAULT 'active',
  ADD COLUMN IF NOT EXISTS validated_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS validated_by_account_id INTEGER REFERENCES facility_accounts(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS validation_method VARCHAR(16),
  ADD COLUMN IF NOT EXISTS ticket_last_event_at TIMESTAMPTZ;

UPDATE facility_appointments
SET
  ticket_code = CONCAT(
    'RCC-FAC-',
    UPPER(SUBSTRING(MD5(CONCAT('facility_appointments:', id::text, ':', COALESCE(created_at::text, NOW()::text))) FROM 1 FOR 8))
  ),
  ticket_last_event_at = COALESCE(ticket_last_event_at, updated_at, created_at, NOW())
WHERE ticket_code IS NULL;

ALTER TABLE facility_appointments
  ALTER COLUMN ticket_code SET NOT NULL;

ALTER TABLE facility_appointments
  DROP CONSTRAINT IF EXISTS chk_facility_appointment_ticket_status;

ALTER TABLE facility_appointments
  ADD CONSTRAINT chk_facility_appointment_ticket_status
  CHECK (ticket_status IN ('active', 'used', 'canceled', 'expired'));

ALTER TABLE facility_appointments
  DROP CONSTRAINT IF EXISTS chk_facility_appointment_validation_method;

ALTER TABLE facility_appointments
  ADD CONSTRAINT chk_facility_appointment_validation_method
  CHECK (validation_method IS NULL OR validation_method IN ('manual', 'qr', 'otp'));

CREATE UNIQUE INDEX IF NOT EXISTS uq_facility_appointments_ticket_code
  ON facility_appointments(ticket_code);

CREATE INDEX IF NOT EXISTS idx_facility_appointments_ticket_status
  ON facility_appointments(ticket_status);

CREATE INDEX IF NOT EXISTS idx_facility_appointments_validated_by_account_id
  ON facility_appointments(validated_by_account_id);

COMMIT;
