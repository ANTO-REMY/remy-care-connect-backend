-- Migration 040: Facility dashboard appointments (Milestone 4)
-- Date: 2026-04-15

CREATE TABLE IF NOT EXISTS facility_appointments (
  id SERIAL PRIMARY KEY,
  facility_id BIGINT NOT NULL REFERENCES health_facilities(id) ON DELETE CASCADE,
  mother_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
  mother_name VARCHAR(128) NOT NULL,
  scheduled_time TIMESTAMP NOT NULL,
  appointment_type VARCHAR(64),
  status VARCHAR(32) NOT NULL DEFAULT 'scheduled',
  assigned_staff_account_id BIGINT REFERENCES facility_accounts(id) ON DELETE SET NULL,
  created_by_account_id BIGINT REFERENCES facility_accounts(id) ON DELETE SET NULL,
  notes TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
  updated_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
  CONSTRAINT chk_facility_appointments_status CHECK (status IN ('scheduled', 'assigned', 'completed', 'canceled'))
);

CREATE INDEX IF NOT EXISTS idx_facility_appointments_facility ON facility_appointments(facility_id);
CREATE INDEX IF NOT EXISTS idx_facility_appointments_scheduled_time ON facility_appointments(scheduled_time);
CREATE INDEX IF NOT EXISTS idx_facility_appointments_assigned_staff ON facility_appointments(assigned_staff_account_id);
