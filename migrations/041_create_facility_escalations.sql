-- Migration 041: Facility escalation workflow parity
-- Date: 2026-04-15

CREATE TABLE IF NOT EXISTS facility_escalations (
  id SERIAL PRIMARY KEY,
  facility_id BIGINT NOT NULL REFERENCES health_facilities(id) ON DELETE CASCADE,
  mother_id BIGINT REFERENCES mothers(id) ON DELETE SET NULL,
  mother_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
  mother_name VARCHAR(128) NOT NULL,
  chw_id BIGINT REFERENCES chws(id) ON DELETE SET NULL,
  chw_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
  checkin_id BIGINT REFERENCES daily_checkin(id) ON DELETE SET NULL,
  case_description TEXT NOT NULL,
  issue_type VARCHAR(64),
  notes TEXT,
  priority VARCHAR(16) NOT NULL DEFAULT 'medium',
  status VARCHAR(20) NOT NULL DEFAULT 'received',
  assigned_staff_account_id BIGINT REFERENCES facility_accounts(id) ON DELETE SET NULL,
  assigned_staff_role VARCHAR(20),
  created_by_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
  updated_by_account_id BIGINT REFERENCES facility_accounts(id) ON DELETE SET NULL,
  created_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
  updated_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
  checked_out_at TIMESTAMP,
  CONSTRAINT chk_facility_escalations_priority CHECK (priority IN ('low', 'medium', 'high', 'critical')),
  CONSTRAINT chk_facility_escalations_status CHECK (status IN ('received', 'in_progress', 'checked_out'))
);

CREATE INDEX IF NOT EXISTS idx_facility_escalations_facility ON facility_escalations(facility_id);
CREATE INDEX IF NOT EXISTS idx_facility_escalations_status ON facility_escalations(status);
CREATE INDEX IF NOT EXISTS idx_facility_escalations_assigned_staff ON facility_escalations(assigned_staff_account_id);
CREATE INDEX IF NOT EXISTS idx_facility_escalations_mother ON facility_escalations(mother_id);
CREATE INDEX IF NOT EXISTS idx_facility_escalations_chw ON facility_escalations(chw_id);
CREATE INDEX IF NOT EXISTS idx_facility_escalations_created ON facility_escalations(created_at DESC);
