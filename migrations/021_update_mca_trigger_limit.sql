-- Update trigger function to enforce a max of 20 active mothers per CHW, aligning with the Python application logic.
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

  -- Enforce max 20 active mothers per CHW
  IF NEW.status = 'active' THEN
    PERFORM pg_advisory_xact_lock(NEW.chw_id::BIGINT);
    SELECT COUNT(*) INTO active_count
    FROM mother_chw_assignments
    WHERE chw_id = NEW.chw_id
      AND status = 'active'
      AND (TG_OP = 'INSERT' OR id <> NEW.id);
    IF active_count >= 20 THEN
      RAISE EXCEPTION 'CHW % already has 20 active mothers', NEW.chw_id;
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
