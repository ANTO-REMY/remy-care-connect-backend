-- 025_create_daily_checkin_hidden_for_user.sql
-- Per-user daily check-in visibility (hide from dashboard without deleting source row)

CREATE TABLE IF NOT EXISTS daily_checkin_hidden_for_user (
    id SERIAL PRIMARY KEY,
    checkin_id INTEGER NOT NULL REFERENCES daily_checkin(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    hidden_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reason TEXT,
    CONSTRAINT uq_daily_checkin_hidden_user UNIQUE (checkin_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_daily_checkin_hidden_for_user_user_id
    ON daily_checkin_hidden_for_user (user_id);

CREATE INDEX IF NOT EXISTS idx_daily_checkin_hidden_for_user_checkin_id
    ON daily_checkin_hidden_for_user (checkin_id);
