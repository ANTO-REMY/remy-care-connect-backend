-- 030_create_resources_simple.sql
-- Alternative migration with simpler constraint handling

CREATE TABLE IF NOT EXISTS resources (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    target_role VARCHAR(50) NOT NULL CHECK (target_role IN ('mother', 'chw', 'nurse')),
    content_type VARCHAR(50),
    url VARCHAR(255),
    thumbnail VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create index on target_role for filtering performance
CREATE INDEX IF NOT EXISTS idx_resources_target_role ON resources(target_role);