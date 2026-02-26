-- Migration to make mother profile fields NOT NULL
-- This ensures dob, due_date, and location are required during registration

-- First, update any existing NULL values with temporary data
-- (You may need to manually update these with real data if you have existing mothers)
UPDATE mothers 
SET dob = COALESCE(dob, CURRENT_DATE - INTERVAL '25 years'),
    due_date = COALESCE(due_date, CURRENT_DATE + INTERVAL '9 months'),
    location = COALESCE(location, 'Not Specified')
WHERE dob IS NULL OR due_date IS NULL OR location IS NULL;

-- Now alter the table to make these columns NOT NULL
ALTER TABLE mothers 
  ALTER COLUMN dob SET NOT NULL,
  ALTER COLUMN due_date SET NOT NULL,
  ALTER COLUMN location SET NOT NULL;

-- Add comment to document the change
COMMENT ON COLUMN mothers.dob IS 'Mother date of birth - required during registration';
COMMENT ON COLUMN mothers.due_date IS 'Expected due date - required during registration';
COMMENT ON COLUMN mothers.location IS 'Mother location - required during registration';
