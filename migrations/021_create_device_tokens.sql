-- Migration 021: Create device_tokens table for Firebase Cloud Messaging
-- Each device a user logs in from gets its own FCM registration token.
-- Used by the push-notification layer to deliver offline alerts.

CREATE TABLE IF NOT EXISTS device_tokens (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    fcm_token   TEXT    NOT NULL,
    device_info TEXT,                             -- e.g. "Android 14 / Chrome 125"
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, fcm_token)
);

CREATE INDEX IF NOT EXISTS idx_device_tokens_user ON device_tokens(user_id);
