-- Mothers table
CREATE TABLE mothers (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  mother_name VARCHAR NOT NULL,
  dob DATE,
  due_date DATE,
  location VARCHAR,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


