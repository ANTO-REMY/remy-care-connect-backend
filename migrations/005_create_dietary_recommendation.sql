-- dietary_recommendation.sql
-- Table for dietary recommendations for mothers
CREATE TABLE dietary_recommendation (
  id SERIAL PRIMARY KEY,
  title VARCHAR NOT NULL,
  content TEXT NOT NULL, -- dietary advice or link
  target_group VARCHAR, -- e.g., 'first_trimester', 'anemia', etc.
  created_by INTEGER REFERENCES users(id),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
