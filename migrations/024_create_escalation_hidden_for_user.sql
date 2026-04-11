-- 024_create_escalation_hidden_for_user.sql
-- Per-user escalation visibility (soft-delete from dashboard without removing source row)

CREATE TABLE IF NOT EXISTS escalation_hidden_for_user (
    id SERIAL PRIMARY KEY,
    escalation_id INTEGER NOT NULL REFERENCES escalations(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    hidden_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reason TEXT,
    CONSTRAINT uq_escalation_hidden_user UNIQUE (escalation_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_escalation_hidden_for_user_user_id
    ON escalation_hidden_for_user (user_id);

CREATE INDEX IF NOT EXISTS idx_escalation_hidden_for_user_escalation_id
    ON escalation_hidden_for_user (escalation_id);
