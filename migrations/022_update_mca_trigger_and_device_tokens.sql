-- Migration 022: Combined patch
-- Part A: Update MCA trigger to cap active mothers per CHW at 20
--         (moves logic from application layer into the DB)
-- Part B: Create device_tokens table for Firebase Cloud Messaging push notifications

-- ── Part A: enforce max-20-active-mothers trigger ────────────────────────────

CREATE OR REPLACE FUNCTION trg_mca_validate()
RETURNS TRIGGER AS $$
DECLARE
  chw_exists   INTEGER;
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

-- Re-attach trigger (DROP + CREATE to be idempotent)
DROP TRIGGER IF EXISTS trg_mca_validate ON mother_chw_assignments;
CREATE TRIGGER trg_mca_validate
  BEFORE INSERT OR UPDATE ON mother_chw_assignments
  FOR EACH ROW EXECUTE FUNCTION trg_mca_validate();

-- ── Part B: device_tokens for FCM push notifications ─────────────────────────
-- Each device a user logs in from gets its own FCM registration token.
-- Used by the push-notification layer to deliver offline alerts.

CREATE TABLE IF NOT EXISTS device_tokens (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    fcm_token   TEXT    NOT NULL,
    device_info TEXT,                               -- e.g. "Android 14 / Chrome 125"
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, fcm_token)
);

CREATE INDEX IF NOT EXISTS idx_device_tokens_user ON device_tokens(user_id);
