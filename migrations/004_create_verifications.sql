-- Verifications (OTP storage)
CREATE TABLE verifications (
  id SERIAL PRIMARY KEY,
  user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
  phone_number VARCHAR NOT NULL,
  code VARCHAR NOT NULL CHECK (code ~ '^[0-9]{5}$'), -- enforce 5-digit numeric OTP
  status VARCHAR NOT NULL CHECK (status IN ('pending', 'verified', 'expired')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ NOT NULL
);
