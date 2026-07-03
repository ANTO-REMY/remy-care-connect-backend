-- Migration 044: Phase A - Auth identity/table alignment groundwork
-- Date: 2026-04-17
-- Goal:
--   1) Expand users role constraint to include doctor.
--   2) Expand facility_staff to support invite-first verification flow and richer querying.
--   3) Preserve backward compatibility with existing facility account data.

BEGIN;

-- 1) Expand users.role check to include doctor.
DO $$
DECLARE
  c RECORD;
BEGIN
  FOR c IN
    SELECT conname
    FROM pg_constraint
    WHERE conrelid = 'users'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) ILIKE '%role%'
      AND pg_get_constraintdef(oid) ILIKE '%mother%'
      AND pg_get_constraintdef(oid) ILIKE '%chw%'
      AND pg_get_constraintdef(oid) ILIKE '%nurse%'
  LOOP
    EXECUTE format('ALTER TABLE users DROP CONSTRAINT IF EXISTS %I', c.conname);
  END LOOP;
END $$;

ALTER TABLE users
  ADD CONSTRAINT chk_users_role_v2
  CHECK (role IN ('mother', 'chw', 'nurse', 'doctor'));

-- 2) Expand facility_staff for invite-first and role-profile query use.
ALTER TABLE facility_staff
  ALTER COLUMN account_id DROP NOT NULL,
  ADD COLUMN IF NOT EXISTS user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS invitation_id BIGINT REFERENCES facility_invitations(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS invitation_phone VARCHAR(20),
  ADD COLUMN IF NOT EXISTS first_name VARCHAR(64),
  ADD COLUMN IF NOT EXISTS last_name VARCHAR(64) NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS is_verified BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP;

ALTER TABLE facility_staff
  DROP CONSTRAINT IF EXISTS chk_facility_staff_status;

ALTER TABLE facility_staff
  ADD CONSTRAINT chk_facility_staff_status
  CHECK (status IN ('pending_verification', 'active', 'inactive', 'removed'));

-- Backfill first/last/contact from linked account when available.
UPDATE facility_staff fs
SET
  first_name = COALESCE(fs.first_name, fa.first_name),
  last_name = COALESCE(fs.last_name, fa.last_name, ''),
  invitation_phone = COALESCE(fs.invitation_phone, fa.phone_number),
  is_verified = CASE
    WHEN fs.status = 'active' THEN TRUE
    ELSE fs.is_verified
  END,
  verified_at = CASE
    WHEN fs.status = 'active' AND fs.verified_at IS NULL THEN NOW()
    ELSE fs.verified_at
  END
FROM facility_accounts fa
WHERE fs.account_id = fa.id;

-- Best-effort link to users identity by account phone/email.
UPDATE facility_staff fs
SET user_id = u.id
FROM facility_accounts fa
JOIN users u
  ON (fa.phone_number IS NOT NULL AND u.phone_number = fa.phone_number)
  OR (fa.email IS NOT NULL AND u.email = fa.email)
WHERE fs.account_id = fa.id
  AND fs.user_id IS NULL;

-- Helpful query indexes for login and staff list views.
CREATE INDEX IF NOT EXISTS idx_fs_user_id ON facility_staff(user_id);
CREATE INDEX IF NOT EXISTS idx_fs_invitation_id ON facility_staff(invitation_id);
CREATE INDEX IF NOT EXISTS idx_fs_invitation_phone ON facility_staff(invitation_phone);
CREATE INDEX IF NOT EXISTS idx_fs_status ON facility_staff(status);
CREATE INDEX IF NOT EXISTS idx_fs_facility_status ON facility_staff(facility_id, status);
CREATE INDEX IF NOT EXISTS idx_fs_facility_contact ON facility_staff(facility_id, invitation_phone);

COMMIT;
