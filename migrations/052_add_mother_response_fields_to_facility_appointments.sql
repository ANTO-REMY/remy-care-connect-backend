ALTER TABLE facility_appointments
  ADD COLUMN IF NOT EXISTS mother_response_status VARCHAR(16),
  ADD COLUMN IF NOT EXISTS mother_response_note TEXT,
  ADD COLUMN IF NOT EXISTS mother_responded_at TIMESTAMPTZ;

ALTER TABLE facility_appointments
  DROP CONSTRAINT IF EXISTS chk_facility_appointments_mother_response_status;

ALTER TABLE facility_appointments
  ADD CONSTRAINT chk_facility_appointments_mother_response_status
  CHECK (
    mother_response_status IS NULL
    OR mother_response_status IN ('confirmed', 'declined')
  );
