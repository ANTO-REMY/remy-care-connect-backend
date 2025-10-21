-- Mother-CHW Assignments table
DROP TABLE IF EXISTS mother_chw_assignments CASCADE;

CREATE TABLE mother_chw_assignments (
  id SERIAL PRIMARY KEY,
  mother_id INTEGER NOT NULL REFERENCES mothers(id) ON DELETE CASCADE,
  mother_name VARCHAR NOT NULL,
  chw_id INTEGER NOT NULL REFERENCES chws(id) ON DELETE CASCADE,
  chw_name VARCHAR NOT NULL,
  assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  status VARCHAR NOT NULL CHECK (status IN ('active', 'inactive'))
);

-- Helpful indexes
CREATE INDEX idx_mca_mother_id ON mother_chw_assignments(mother_id);
CREATE INDEX idx_mca_chw_id_status ON mother_chw_assignments(chw_id, status);

-- Trigger function to validate CHW assignments
CREATE OR REPLACE FUNCTION trg_mca_validate()
RETURNS TRIGGER AS $$
DECLARE
  chw_exists INTEGER;
  active_count INTEGER;
BEGIN
  -- Ensure CHW exists
  SELECT COUNT(*) INTO chw_exists FROM chws WHERE id = NEW.chw_id;
  IF chw_exists = 0 THEN
    RAISE EXCEPTION 'CHW with id % does not exist', NEW.chw_id;
  END IF;

  -- Enforce max 2 active mothers per CHW
  IF NEW.status = 'active' THEN
    PERFORM pg_advisory_xact_lock(NEW.chw_id::BIGINT);
    SELECT COUNT(*) INTO active_count
    FROM mother_chw_assignments
    WHERE chw_id = NEW.chw_id
      AND status = 'active'
      AND (TG_OP = 'INSERT' OR id <> NEW.id);
    IF active_count >= 2 THEN
      RAISE EXCEPTION 'CHW % already has 2 active mothers', NEW.chw_id;
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Attach trigger
DROP TRIGGER IF EXISTS trg_mca_before_ins_upd ON mother_chw_assignments;

CREATE TRIGGER trg_mca_before_ins_upd
BEFORE INSERT OR UPDATE OF chw_id, status
ON mother_chw_assignments
FOR EACH ROW
EXECUTE FUNCTION trg_mca_validate();
