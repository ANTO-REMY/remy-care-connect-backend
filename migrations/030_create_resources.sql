-- 030_create_resources.sql
-- Educational resources for mothers, CHWs, and nurses.

CREATE TABLE IF NOT EXISTS resources (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    target_role VARCHAR(50) NOT NULL,
    content_type VARCHAR(50),
    url VARCHAR(255),
    thumbnail VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Add constraint for target_role (PostgreSQL compatible)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'chk_resources_target_role' 
        AND table_name = 'resources'
    ) THEN
        ALTER TABLE resources ADD CONSTRAINT chk_resources_target_role 
            CHECK (target_role IN ('mother', 'chw', 'nurse'));
    END IF;
END $$;

-- Create index on target_role for filtering performance
CREATE INDEX IF NOT EXISTS idx_resources_target_role ON resources(target_role);