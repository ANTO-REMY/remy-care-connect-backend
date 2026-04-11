-- Migration 035: Create Reminders table
CREATE TABLE reminders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL,
    time_string VARCHAR(32) NOT NULL,
    frequency VARCHAR(50) NOT NULL DEFAULT 'daily',
    icon VARCHAR(32),
    last_completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
