-- 009_create_next_of_kin.sql
CREATE TABLE IF NOT EXISTS next_of_kin (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES mothers(id) ON DELETE CASCADE,
    mother_name VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(32) NOT NULL,
    sex VARCHAR(8) NOT NULL,
    relationship VARCHAR(64) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_next_of_kin_user_id ON next_of_kin(user_id);
