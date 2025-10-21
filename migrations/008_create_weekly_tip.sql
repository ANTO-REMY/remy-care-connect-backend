-- weekly_tip.sql
-- Stores weekly tips for mothers
CREATE TABLE weekly_tip (
  id SERIAL PRIMARY KEY,
  week INTEGER NOT NULL,
  category VARCHAR NOT NULL,
  title VARCHAR NOT NULL,
  content TEXT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_by INTEGER REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
