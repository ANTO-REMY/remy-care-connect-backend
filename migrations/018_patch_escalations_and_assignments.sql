-- ============================================================
-- Migration 018: Patch escalations + assignments for full feature parity
-- ============================================================

-- ── 1. ESCALATIONS ──────────────────────────────────────────────────────────
-- Drop old status constraint and add new one that includes 'in_progress'
ALTER TABLE escalations DROP CONSTRAINT IF EXISTS escalations_status_check;
ALTER TABLE escalations
  ADD CONSTRAINT escalations_status_check
  CHECK (status IN ('pending', 'in_progress', 'resolved', 'rejected'));

-- Add priority column (default 'medium' for existing rows)
ALTER TABLE escalations ADD COLUMN IF NOT EXISTS priority VARCHAR NOT NULL DEFAULT 'medium';
ALTER TABLE escalations ADD CONSTRAINT escalations_priority_check
  CHECK (priority IN ('low', 'medium', 'high', 'critical'));

-- Add issue_type column
ALTER TABLE escalations ADD COLUMN IF NOT EXISTS issue_type VARCHAR;

-- Add notes column (CHW-authored notes)
ALTER TABLE escalations ADD COLUMN IF NOT EXISTS notes TEXT;

-- Add index for priority (useful for nurse dashboard filtering)
CREATE INDEX IF NOT EXISTS idx_escalations_priority ON escalations(priority);
CREATE INDEX IF NOT EXISTS idx_escalations_created_at ON escalations(created_at DESC);

-- ── 2. MOTHER-CHW ASSIGNMENTS ─────────────────────────────────────────────────
-- The trigger currently blocks > 2 active mothers per CHW.
-- We raise this to a more operationally realistic limit (20), while keeping
-- the guard as a safety net against runaway data bugs.
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

  -- Enforce max 20 active mothers per CHW (adjusted from 2)
  IF NEW.status = 'active' THEN
    PERFORM pg_advisory_xact_lock(NEW.chw_id::BIGINT);
    SELECT COUNT(*) INTO active_count
    FROM mother_chw_assignments
    WHERE chw_id = NEW.chw_id
      AND status = 'active'
      AND (TG_OP = 'INSERT' OR id <> NEW.id);
    IF active_count >= 20 THEN
      RAISE EXCEPTION 'CHW % already has the maximum number of active mothers assigned', NEW.chw_id;
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ── 3. APPOINTMENT SCHEDULE – add missing updated_at trigger ─────────────────
-- Auto-update updated_at on every UPDATE
CREATE OR REPLACE FUNCTION trg_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_appointment_updated_at ON appointment_schedule;
CREATE TRIGGER trg_appointment_updated_at
BEFORE UPDATE ON appointment_schedule
FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

-- Add index on scheduled_time for calendar queries
CREATE INDEX IF NOT EXISTS idx_appointment_scheduled_time ON appointment_schedule(scheduled_time);
CREATE INDEX IF NOT EXISTS idx_appointment_status_time ON appointment_schedule(status, scheduled_time);
