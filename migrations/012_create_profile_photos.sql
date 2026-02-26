-- 012_create_profile_photos.sql
-- Creates the profile_photos table for user profile image uploads.
-- Run in DataGrip after the users table is clean and correct.

CREATE TABLE IF NOT EXISTS profile_photos (
  id           SERIAL PRIMARY KEY,
  user_id      INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role         VARCHAR      NOT NULL CHECK (role IN ('mother', 'chw', 'nurse')),
  file_name    VARCHAR      NOT NULL,           -- original sanitised filename
  file_url     VARCHAR      NOT NULL,           -- relative path served by Flask static
  mime_type    VARCHAR      NOT NULL DEFAULT 'image/jpeg',
  file_size    INTEGER,                         -- size in bytes
  is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
  uploaded_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- One active photo per user at any time
CREATE UNIQUE INDEX IF NOT EXISTS uidx_profile_photos_active_user
  ON profile_photos (user_id)
  WHERE is_active = TRUE;

-- Fast lookup by user
CREATE INDEX IF NOT EXISTS idx_profile_photos_user_id
  ON profile_photos (user_id);
