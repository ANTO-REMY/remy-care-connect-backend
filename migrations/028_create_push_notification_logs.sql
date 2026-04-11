-- 028_create_push_notification_logs.sql
-- Persist FCM delivery telemetry for observability.

CREATE TABLE IF NOT EXISTS push_notification_logs (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event VARCHAR(128) NOT NULL,
  title VARCHAR(255) NOT NULL,
  body TEXT NOT NULL,
  token_count INTEGER NOT NULL DEFAULT 0,
  success_count INTEGER NOT NULL DEFAULT 0,
  failure_count INTEGER NOT NULL DEFAULT 0,
  stale_token_count INTEGER NOT NULL DEFAULT 0,
  status VARCHAR(32) NOT NULL,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_push_notification_logs_user_created
  ON push_notification_logs(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_push_notification_logs_event
  ON push_notification_logs(event);
