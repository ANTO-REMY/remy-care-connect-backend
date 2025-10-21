-- medical_record_type.sql
-- Lookup table for types of medical records
CREATE TABLE medical_record_type (
  id SERIAL PRIMARY KEY,
  name VARCHAR NOT NULL UNIQUE,
  description TEXT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_by INTEGER REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Example insertions (can be adjusted or removed in production)
INSERT INTO medical_record_type (name, description, created_by) VALUES
  ('checkup', 'Routine health checkup', 1),
  ('vaccination', 'Vaccination record', 1),
  ('lab_test', 'Lab test result', 1);
