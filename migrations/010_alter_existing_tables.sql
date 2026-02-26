-- 010_alter_existing_tables.sql
-- Run this in DataGrip (or psql) against the live remyafya database.
-- ALWAYS TAKE A BACKUP BEFORE RUNNING.

-- ============================================================
-- 1. mothers table: make dob, due_date, location nullable
--    (mothers complete their profile from the dashboard after registration)
-- ============================================================
ALTER TABLE mothers
  ALTER COLUMN dob       DROP NOT NULL,
  ALTER COLUMN due_date  DROP NOT NULL,
  ALTER COLUMN location  DROP NOT NULL;


-- ============================================================
-- 2. users table: rename `name` → `first_name`, add `last_name`
-- ============================================================

-- Step 2a: Rename the existing name column to first_name
ALTER TABLE users RENAME COLUMN name TO first_name;

-- Step 2b: Add last_name column (nullable initially for existing rows)
ALTER TABLE users ADD COLUMN last_name VARCHAR;

-- Step 2c: Backfill last_name for existing rows that have a space in first_name
--          e.g. "John Doe" → first_name="John", last_name="Doe"
UPDATE users
  SET
    last_name  = NULLIF(TRIM(SUBSTRING(first_name FROM POSITION(' ' IN first_name) + 1)), ''),
    first_name = SPLIT_PART(first_name, ' ', 1)
  WHERE first_name LIKE '% %';

-- Step 2d: Default last_name to '' for rows with no space (single-name entries)
UPDATE users SET last_name = '' WHERE last_name IS NULL;

-- Step 2e: Enforce NOT NULL now that all rows are populated
ALTER TABLE users ALTER COLUMN last_name SET NOT NULL;


-- ============================================================
-- 3. Add email column to users (nullable — not required at registration)
-- ============================================================
ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR;


-- ============================================================
-- 4. Reorder users columns via table recreation
--    PostgreSQL does not support ALTER TABLE ... REORDER COLUMNS,
--    so we drop child FK constraints first, rename the existing
--    table, create a fresh one with the desired column order,
--    copy all data, re-add FKs, then drop the old table.
--
--    Desired order:
--      id, phone_number, first_name, last_name, email,
--      pin_hash, role, is_verified, created_at, updated_at
-- ============================================================

-- Step 4a: Drop all FK constraints on child tables that reference users
--          (they will be re-added after the new table is created)
ALTER TABLE user_sessions  DROP CONSTRAINT IF EXISTS user_sessions_user_id_fkey;
ALTER TABLE mothers        DROP CONSTRAINT IF EXISTS mothers_user_id_fkey;
ALTER TABLE chws           DROP CONSTRAINT IF EXISTS chws_user_id_fkey;
ALTER TABLE nurses         DROP CONSTRAINT IF EXISTS nurses_user_id_fkey;
ALTER TABLE verifications  DROP CONSTRAINT IF EXISTS verifications_user_id_fkey;

-- Step 4b: Rename current table to a temp name
ALTER TABLE users RENAME TO users_old;

-- Step 4c: Create new table with correct column order
CREATE TABLE users (
  id           SERIAL PRIMARY KEY,
  phone_number VARCHAR NOT NULL UNIQUE,
  first_name   VARCHAR NOT NULL,
  last_name    VARCHAR NOT NULL,
  email        VARCHAR,
  pin_hash     VARCHAR NOT NULL,
  role         VARCHAR NOT NULL CHECK (role IN ('mother', 'chw', 'nurse')),
  is_verified  BOOLEAN NOT NULL DEFAULT FALSE,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Step 4d: Copy all data from old table into new table
INSERT INTO users (id, phone_number, first_name, last_name, email, pin_hash, role, is_verified, created_at, updated_at)
SELECT id, phone_number, first_name, last_name, email, pin_hash, role, is_verified, created_at, updated_at
FROM users_old;

-- Step 4e: Reset the serial sequence to continue from the right value
SELECT setval('users_id_seq', (SELECT MAX(id) FROM users));

-- Step 4f: Re-add FK constraints pointing to the new users table
ALTER TABLE user_sessions  ADD CONSTRAINT user_sessions_user_id_fkey  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE mothers        ADD CONSTRAINT mothers_user_id_fkey         FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE chws           ADD CONSTRAINT chws_user_id_fkey            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE nurses         ADD CONSTRAINT nurses_user_id_fkey          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE verifications  ADD CONSTRAINT verifications_user_id_fkey   FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- Step 4g: Drop the old table (safe now — no FKs depend on it)
DROP TABLE users_old;



-- ============================================================
-- 5. Sync role profile tables: rebuild *_name from first+last
-- ============================================================
UPDATE chws
  SET chw_name = (
    SELECT TRIM(u.first_name || ' ' || u.last_name)
    FROM users u WHERE u.id = chws.user_id
  );

UPDATE nurses
  SET nurse_name = (
    SELECT TRIM(u.first_name || ' ' || u.last_name)
    FROM users u WHERE u.id = nurses.user_id
  );

UPDATE mothers
  SET mother_name = (
    SELECT TRIM(u.first_name || ' ' || u.last_name)
    FROM users u WHERE u.id = mothers.user_id
  );


-- ============================================================
-- 6. mother_chw_assignments: ensure required columns exist
--    (already present if migration 005 was run; idempotent guards)
-- ============================================================
ALTER TABLE mother_chw_assignments
  ADD COLUMN IF NOT EXISTS mother_name VARCHAR NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS chw_name    VARCHAR NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS status      VARCHAR      NOT NULL DEFAULT 'active';

-- Backfill names for any existing rows
UPDATE mother_chw_assignments mca
  SET
    mother_name = (SELECT mother_name FROM mothers WHERE id = mca.mother_id),
    chw_name    = (SELECT chw_name    FROM chws    WHERE id = mca.chw_id);

-- Add check constraint if missing
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'chk_assignment_status'
  ) THEN
    ALTER TABLE mother_chw_assignments
      ADD CONSTRAINT chk_assignment_status CHECK (status IN ('active', 'inactive'));
  END IF;
END $$;
