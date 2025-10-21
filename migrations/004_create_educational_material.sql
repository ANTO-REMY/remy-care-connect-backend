-- educational_material.sql
-- Table for educational resources for CHWs and nurses
CREATE TABLE educational_material (
  id SERIAL PRIMARY KEY,
  title VARCHAR NOT NULL,
  content TEXT, -- text, markdown, or a link (optional if file_url is provided)
  file_url VARCHAR, -- optional: URL or path to uploaded file
  category VARCHAR,
  audience VARCHAR NOT NULL CHECK (audience IN ('chw', 'nurse', 'both')),
  created_by INTEGER REFERENCES users(id),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
