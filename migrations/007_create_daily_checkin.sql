-- daily_checkin.sql
-- Stores daily check-in responses from mothers
CREATE TABLE daily_checkin (
  id SERIAL PRIMARY KEY,
  mother_id INTEGER NOT NULL REFERENCES mothers(id) ON DELETE CASCADE,
  response VARCHAR NOT NULL CHECK (response IN ('ok', 'not_ok')),
  comment TEXT,
  channel VARCHAR NOT NULL CHECK (channel IN ('app', 'whatsapp', 'sms')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
