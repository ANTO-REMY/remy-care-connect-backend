-- 029_create_user_notifications.sql
-- Persistent in-app notification inbox per user role.

CREATE TABLE IF NOT EXISTS user_notifications (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event_type VARCHAR(128) NOT NULL,
  title VARCHAR(255) NOT NULL,
  message TEXT NOT NULL,
  url VARCHAR(255),
  entity_type VARCHAR(64),
  entity_id INTEGER,
  is_read BOOLEAN NOT NULL DEFAULT FALSE,
  read_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_notifications_user_created
  ON user_notifications(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_notifications_user_unread
  ON user_notifications(user_id, is_read, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_notifications_event_type
  ON user_notifications(event_type);
