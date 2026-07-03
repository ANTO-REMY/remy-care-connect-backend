-- Migration 050: Mother-CHW auto-assignment invariants and audit fields

ALTER TABLE mother_chw_assignments
  ADD COLUMN IF NOT EXISTS assignment_method VARCHAR(32) NOT NULL DEFAULT 'manual',
  ADD COLUMN IF NOT EXISTS reassigned_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS reassignment_reason TEXT;

UPDATE mother_chw_assignments
SET assignment_method = 'manual'
WHERE assignment_method IS NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chk_assignment_method'
  ) THEN
    ALTER TABLE mother_chw_assignments
      ADD CONSTRAINT chk_assignment_method
      CHECK (assignment_method IN ('manual', 'auto_ward_match'));
  END IF;
END $$;

-- Normalize any stale duplicate active assignments so one mother can have only one active CHW.
WITH ranked AS (
  SELECT
    id,
    mother_id,
    ROW_NUMBER() OVER (
      PARTITION BY mother_id
      ORDER BY assigned_at DESC NULLS LAST, id DESC
    ) AS rn
  FROM mother_chw_assignments
  WHERE status = 'active'
)
UPDATE mother_chw_assignments mca
SET
  status = 'inactive',
  reassigned_at = NOW(),
  reassignment_reason = 'migration_duplicate_active_cleanup'
FROM ranked
WHERE mca.id = ranked.id
  AND ranked.rn > 1;

CREATE INDEX IF NOT EXISTS idx_mca_mother_active
  ON mother_chw_assignments(mother_id)
  WHERE status = 'active';

CREATE UNIQUE INDEX IF NOT EXISTS uq_mca_one_active_mother
  ON mother_chw_assignments(mother_id)
  WHERE status = 'active';
