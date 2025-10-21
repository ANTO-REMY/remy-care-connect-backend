-- Escalations (CHW escalates to Nurse)
CREATE TABLE escalations (
  id SERIAL PRIMARY KEY,
  chw_id INTEGER NOT NULL REFERENCES chws(id) ON DELETE CASCADE,
  chw_name VARCHAR NOT NULL,
  nurse_id INTEGER NOT NULL REFERENCES nurses(id) ON DELETE CASCADE,
  nurse_name VARCHAR NOT NULL,
  mother_id INTEGER REFERENCES mothers(id) ON DELETE CASCADE,
  mother_name VARCHAR NOT NULL,
  case_description TEXT NOT NULL,
  status VARCHAR NOT NULL CHECK (status IN ('pending', 'resolved', 'rejected')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  resolved_at TIMESTAMPTZ NULL
);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_escalations_chw_id ON escalations(chw_id);
CREATE INDEX IF NOT EXISTS idx_escalations_nurse_id ON escalations(nurse_id);
CREATE INDEX IF NOT EXISTS idx_escalations_mother_id ON escalations(mother_id);
CREATE INDEX IF NOT EXISTS idx_escalations_status ON escalations(status);

-- Trigger function to ensure CHW and Nurse types
CREATE OR REPLACE FUNCTION trg_escalations_validate() RETURNS TRIGGER AS $$
DECLARE
  chw_exists INTEGER;
  nurse_exists INTEGER;
BEGIN
  SELECT COUNT(*) INTO chw_exists FROM chws WHERE id = NEW.chw_id;
  IF chw_exists = 0 THEN
    RAISE EXCEPTION 'CHW % does not exist', NEW.chw_id;
  END IF;

  SELECT COUNT(*) INTO nurse_exists FROM nurses WHERE id = NEW.nurse_id;
  IF nurse_exists = 0 THEN
    RAISE EXCEPTION 'Nurse % does not exist', NEW.nurse_id;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_escalations_before_ins_upd
BEFORE INSERT OR UPDATE OF chw_id, nurse_id
ON escalations
FOR EACH ROW
EXECUTE FUNCTION trg_escalations_validate();

