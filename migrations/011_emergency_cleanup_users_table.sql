-- 011_emergency_cleanup_users_table.sql
-- Run this in DataGrip to fix the two-table mess.
-- Preserves all original data from users_old.
-- Result: one clean `users` table with correct column order.

-- ============================================================
-- STEP 1: Drop ALL FK constraints from every child table
--         (try both old naming styles — IF NOT EXISTS is safe)
-- ============================================================
ALTER TABLE user_sessions  DROP CONSTRAINT IF EXISTS user_sessions_user_id_fkey;
ALTER TABLE mothers        DROP CONSTRAINT IF EXISTS mothers_user_id_fkey;
ALTER TABLE chws           DROP CONSTRAINT IF EXISTS chws_user_id_fkey;
ALTER TABLE nurses         DROP CONSTRAINT IF EXISTS nurses_user_id_fkey;
ALTER TABLE verifications  DROP CONSTRAINT IF EXISTS verifications_user_id_fkey;

-- Also drop alternative names left by previous migration attempts
ALTER TABLE mothers        DROP CONSTRAINT IF EXISTS fk_mothers_user;
ALTER TABLE chws           DROP CONSTRAINT IF EXISTS fk_chws_user;
ALTER TABLE nurses         DROP CONSTRAINT IF EXISTS fk_nurses_user;
ALTER TABLE verifications  DROP CONSTRAINT IF EXISTS fk_verifications_user;


-- ============================================================
-- STEP 2: Drop the new (currently empty) `users` table
-- ============================================================
DROP TABLE IF EXISTS users CASCADE;


-- ============================================================
-- STEP 3: Create a fresh `users` table with correct column order
--         id | phone_number | first_name | last_name | email |
--         pin_hash | role | is_verified | created_at | updated_at
-- ============================================================
CREATE TABLE users (
  id           SERIAL PRIMARY KEY,
  phone_number VARCHAR NOT NULL UNIQUE,
  first_name   VARCHAR NOT NULL,
  last_name    VARCHAR NOT NULL DEFAULT '',
  email        VARCHAR,
  pin_hash     VARCHAR NOT NULL,
  role         VARCHAR NOT NULL CHECK (role IN ('mother', 'chw', 'nurse')),
  is_verified  BOOLEAN NOT NULL DEFAULT FALSE,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ============================================================
-- STEP 4: Copy all data from users_old into the new users table
-- ============================================================
INSERT INTO users (id, phone_number, first_name, last_name, email, pin_hash, role, is_verified, created_at, updated_at)
SELECT
  id,
  phone_number,
  first_name,
  COALESCE(last_name, ''),   -- last_name may be NULL in old table
  email,
  pin_hash,
  role,
  is_verified,
  created_at,
  updated_at
FROM users_old;


-- ============================================================
-- STEP 5: Sync the sequence so new inserts don't conflict
-- ============================================================
SELECT setval('users_id_seq', COALESCE((SELECT MAX(id) FROM users), 1));


-- ============================================================
-- STEP 6: Drop users_old — safe now, no FKs reference it
-- ============================================================
DROP TABLE users_old CASCADE;


-- ============================================================
-- STEP 7: Re-add FK constraints pointing to the new users table
-- ============================================================
ALTER TABLE user_sessions  ADD CONSTRAINT user_sessions_user_id_fkey  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE mothers        ADD CONSTRAINT mothers_user_id_fkey         FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE chws           ADD CONSTRAINT chws_user_id_fkey            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE nurses         ADD CONSTRAINT nurses_user_id_fkey          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE verifications  ADD CONSTRAINT verifications_user_id_fkey   FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;


-- ============================================================
-- STEP 8: Verify result
-- ============================================================
SELECT column_name, data_type, ordinal_position
FROM information_schema.columns
WHERE table_name = 'users'
ORDER BY ordinal_position;
