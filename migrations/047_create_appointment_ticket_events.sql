-- Migration 047: Create appointment ticket audit trail table
-- Date: 2026-07-01

BEGIN;

CREATE TABLE IF NOT EXISTS appointment_ticket_events (
  id BIGSERIAL PRIMARY KEY,
  appointment_source VARCHAR(16) NOT NULL,
  appointment_id INTEGER NOT NULL,
  ticket_code VARCHAR(32) NOT NULL,
  event_type VARCHAR(32) NOT NULL,
  actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  actor_facility_account_id INTEGER REFERENCES facility_accounts(id) ON DELETE SET NULL,
  actor_role VARCHAR(32),
  event_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  notes TEXT,
  CONSTRAINT chk_appointment_ticket_event_source
    CHECK (appointment_source IN ('standard', 'facility')),
  CONSTRAINT chk_appointment_ticket_event_type
    CHECK (event_type IN ('generated', 'rescheduled', 'validated', 'canceled', 'expired', 'regenerated', 'duplicate_validation_attempt')),
  CONSTRAINT chk_appointment_ticket_event_single_actor
    CHECK (NOT (actor_user_id IS NOT NULL AND actor_facility_account_id IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_appointment_ticket_events_ticket_code
  ON appointment_ticket_events(ticket_code);

CREATE INDEX IF NOT EXISTS idx_appointment_ticket_events_source_appointment
  ON appointment_ticket_events(appointment_source, appointment_id);

CREATE INDEX IF NOT EXISTS idx_appointment_ticket_events_event_time
  ON appointment_ticket_events(event_time);

CREATE INDEX IF NOT EXISTS idx_appointment_ticket_events_actor_user_id
  ON appointment_ticket_events(actor_user_id);

CREATE INDEX IF NOT EXISTS idx_appointment_ticket_events_actor_facility_account_id
  ON appointment_ticket_events(actor_facility_account_id);

COMMIT;
