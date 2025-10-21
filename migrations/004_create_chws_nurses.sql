-- CHWs table
CREATE TABLE chws (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  chw_name VARCHAR NOT NULL,
  license_number VARCHAR NOT NULL,
  location VARCHAR NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Nurses table
CREATE TABLE nurses (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  nurse_name VARCHAR NOT NULL,
  license_number VARCHAR NOT NULL,
  location VARCHAR NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- (Optional) Deprecate old healthworkers table
-- DROP TABLE IF EXISTS healthworkers;
