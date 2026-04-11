-- 023_create_appointment_hidden_for_user.sql
-- Per-user appointment visibility (hide from dashboard without deleting source row)

CREATE TABLE IF NOT EXISTS appointment_hidden_for_user (
    id SERIAL PRIMARY KEY,
    appointment_id INTEGER NOT NULL REFERENCES appointment_schedule(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    hidden_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reason TEXT,
    CONSTRAINT uq_appointment_hidden_user UNIQUE (appointment_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_appointment_hidden_for_user_user_id
    ON appointment_hidden_for_user (user_id);

CREATE INDEX IF NOT EXISTS idx_appointment_hidden_for_user_appointment_id
    ON appointment_hidden_for_user (appointment_id);
