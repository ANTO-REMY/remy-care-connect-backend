-- Alter the CHECK constraint for status in escalations table to include 'in_progress'

ALTER TABLE escalations DROP CONSTRAINT IF EXISTS escalations_status_check;
ALTER TABLE escalations ADD CONSTRAINT escalations_status_check CHECK (status IN ('pending', 'in_progress', 'resolved', 'rejected'));
