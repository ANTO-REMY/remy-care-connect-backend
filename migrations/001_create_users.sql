-- Users table
CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  phone_number VARCHAR NOT NULL UNIQUE,
  name VARCHAR NOT NULL,
  pin_hash VARCHAR NOT NULL,
  role VARCHAR NOT NULL CHECK (role IN ('mother', 'chw', 'nurse')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Helpful index on role (optional, keep if queries filter by role)
-- CREATE INDEX idx_users_role ON users(role);

