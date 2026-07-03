-- Migration 038: Create facility_issues table
-- Purpose: Track user-reported issues with health facilities
-- Date: 2026-04-14

-- Facility Issues table (user-reported problems)
CREATE TABLE IF NOT EXISTS facility_issues (
    id SERIAL PRIMARY KEY,
    facility_id BIGINT NOT NULL REFERENCES health_facilities(id) ON DELETE CASCADE,
    reported_by BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Issue classification
    issue_type VARCHAR(50) NOT NULL,               -- closed, wrong_location, wrong_name, wrong_info, other
    description TEXT,
    
    -- Issue lifecycle
    status VARCHAR(50) NOT NULL DEFAULT 'reported', -- reported, acknowledged, in_progress, resolved, rejected
    priority VARCHAR(20) DEFAULT 'medium',          -- low, medium, high
    
    -- Resolution tracking
    resolved_at TIMESTAMP,
    resolved_by BIGINT REFERENCES users(id),
    resolution_notes TEXT,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    updated_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
);

-- Indexes for efficient queries
CREATE INDEX idx_fi_facility ON facility_issues(facility_id);
CREATE INDEX idx_fi_reported_by ON facility_issues(reported_by);
CREATE INDEX idx_fi_status ON facility_issues(status);
CREATE INDEX idx_fi_issue_type ON facility_issues(issue_type);
CREATE INDEX idx_fi_created ON facility_issues(created_at DESC);
CREATE INDEX idx_fi_priority ON facility_issues(priority);

-- Composite index for common query pattern (facility + status)
CREATE INDEX idx_fi_facility_status ON facility_issues(facility_id, status);

-- Check constraints for data integrity
ALTER TABLE facility_issues
ADD CONSTRAINT chk_fi_issue_type 
CHECK (issue_type IN ('closed', 'wrong_location', 'wrong_name', 'wrong_info', 'other'));

ALTER TABLE facility_issues
ADD CONSTRAINT chk_fi_status 
CHECK (status IN ('reported', 'acknowledged', 'in_progress', 'resolved', 'rejected'));

ALTER TABLE facility_issues
ADD CONSTRAINT chk_fi_priority 
CHECK (priority IN ('low', 'medium', 'high'));

-- Comments for documentation
COMMENT ON TABLE facility_issues IS 'User-reported issues with health facilities';
COMMENT ON COLUMN facility_issues.issue_type IS 'Type of issue: closed, wrong_location, wrong_name, wrong_info, other';
COMMENT ON COLUMN facility_issues.status IS 'Issue lifecycle status';
COMMENT ON COLUMN facility_issues.priority IS 'Issue priority for admin triage';
