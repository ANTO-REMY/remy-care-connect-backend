-- Migration 039: Milestone 3 - Facility self-verification and OTP staff onboarding
-- Date: 2026-04-15
-- Note: Facility onboarding is isolated from users table by design.

-- 1) Dedicated facility registration/auth table
CREATE TABLE IF NOT EXISTS facility_accounts (
  id SERIAL PRIMARY KEY,
  facility_id BIGINT NOT NULL REFERENCES health_facilities(id) ON DELETE CASCADE,
  phone_number VARCHAR(20) UNIQUE,
  email VARCHAR(100) UNIQUE,
  first_name VARCHAR(64) NOT NULL,
  last_name VARCHAR(64) NOT NULL DEFAULT '',
  pin_hash VARCHAR(128),
  role VARCHAR(50) NOT NULL,
  profile_completed BOOLEAN NOT NULL DEFAULT FALSE,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
  updated_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
  CONSTRAINT chk_fa_contact CHECK ((phone_number IS NOT NULL) OR (email IS NOT NULL)),
  CONSTRAINT chk_fa_role CHECK (role IN ('admin', 'doctor', 'midwife', 'nurse', 'chw', 'receptionist'))
);

CREATE INDEX IF NOT EXISTS idx_fa_facility_id ON facility_accounts(facility_id);

-- 2) Extend health_facilities for self-claim admin flow
ALTER TABLE health_facilities
  ADD COLUMN IF NOT EXISTS facility_admin_id BIGINT,
  ADD COLUMN IF NOT EXISTS admin_verified_at TIMESTAMP,
  ADD COLUMN IF NOT EXISTS phone VARCHAR(20),
  ADD COLUMN IF NOT EXISTS email VARCHAR(100),
  ADD COLUMN IF NOT EXISTS hours_text TEXT;

ALTER TABLE health_facilities
  DROP CONSTRAINT IF EXISTS health_facilities_facility_admin_id_fkey;

ALTER TABLE health_facilities
  ADD CONSTRAINT health_facilities_facility_admin_id_fkey
  FOREIGN KEY (facility_admin_id) REFERENCES facility_accounts(id);

CREATE INDEX IF NOT EXISTS idx_hf_facility_admin ON health_facilities(facility_admin_id);

-- 3) Facility staff membership table
CREATE TABLE IF NOT EXISTS facility_staff (
  id SERIAL PRIMARY KEY,
  facility_id BIGINT NOT NULL REFERENCES health_facilities(id) ON DELETE CASCADE,
  account_id BIGINT NOT NULL REFERENCES facility_accounts(id) ON DELETE CASCADE,
  role VARCHAR(50) NOT NULL,
  specialty VARCHAR(120),
  status VARCHAR(50) NOT NULL DEFAULT 'active',
  added_by_account_id BIGINT REFERENCES facility_accounts(id),
  added_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
  UNIQUE (facility_id, account_id),
  CONSTRAINT chk_facility_staff_role CHECK (role IN ('admin', 'doctor', 'midwife', 'nurse', 'chw', 'receptionist')),
  CONSTRAINT chk_facility_staff_status CHECK (status IN ('active', 'inactive', 'removed'))
);

CREATE INDEX IF NOT EXISTS idx_fs_facility ON facility_staff(facility_id);
CREATE INDEX IF NOT EXISTS idx_fs_account ON facility_staff(account_id);
CREATE INDEX IF NOT EXISTS idx_fs_role ON facility_staff(role);

-- 4) OTP table for facility invitations and login
CREATE TABLE IF NOT EXISTS otp_tokens (
  id SERIAL PRIMARY KEY,
  phone_number VARCHAR(20),
  email VARCHAR(100),
  otp_code VARCHAR(6) NOT NULL,
  purpose VARCHAR(50) NOT NULL DEFAULT 'facility_login',
  facility_id BIGINT REFERENCES health_facilities(id),
  attempts INT NOT NULL DEFAULT 0,
  max_attempts INT NOT NULL DEFAULT 3,
  is_used BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
  expires_at TIMESTAMP NOT NULL DEFAULT ((CURRENT_TIMESTAMP AT TIME ZONE 'UTC') + INTERVAL '15 minutes'),
  used_at TIMESTAMP,
  CONSTRAINT chk_otp_contact CHECK ((phone_number IS NOT NULL) OR (email IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_otp_phone ON otp_tokens(phone_number);
CREATE INDEX IF NOT EXISTS idx_otp_email ON otp_tokens(email);
CREATE INDEX IF NOT EXISTS idx_otp_expires ON otp_tokens(expires_at);

-- 5) Invitation tracking
CREATE TABLE IF NOT EXISTS facility_invitations (
  id SERIAL PRIMARY KEY,
  facility_id BIGINT NOT NULL REFERENCES health_facilities(id) ON DELETE CASCADE,
  invitation_phone VARCHAR(20),
  invitation_email VARCHAR(100),
  invited_role VARCHAR(50) NOT NULL,
  invited_by BIGINT NOT NULL REFERENCES facility_accounts(id),
  status VARCHAR(50) NOT NULL DEFAULT 'pending',
  otp_id BIGINT REFERENCES otp_tokens(id),
  created_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
  expires_at TIMESTAMP NOT NULL DEFAULT ((CURRENT_TIMESTAMP AT TIME ZONE 'UTC') + INTERVAL '7 days'),
  accepted_at TIMESTAMP,
  CONSTRAINT chk_fi_contact CHECK ((invitation_phone IS NOT NULL) OR (invitation_email IS NOT NULL)),
  CONSTRAINT chk_fi_status CHECK (status IN ('pending', 'accepted', 'expired'))
);

CREATE INDEX IF NOT EXISTS idx_fi_facility ON facility_invitations(facility_id);
CREATE INDEX IF NOT EXISTS idx_fi_phone ON facility_invitations(invitation_phone);
CREATE INDEX IF NOT EXISTS idx_fi_email ON facility_invitations(invitation_email);
CREATE INDEX IF NOT EXISTS idx_fi_status ON facility_invitations(status);
