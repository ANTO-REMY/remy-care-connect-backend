-- appointment_schedule.sql
-- Schedules appointments, supports recurring events
CREATE TABLE appointment_schedule (
  id SERIAL PRIMARY KEY,
  mother_id INTEGER NOT NULL REFERENCES users(id),
  health_worker_id INTEGER NOT NULL REFERENCES users(id),
  scheduled_time TIMESTAMPTZ NOT NULL,
  recurrence_rule VARCHAR, -- e.g., iCal RRULE or custom JSON for frequency
  recurrence_end TIMESTAMPTZ, -- when the recurring series ends
  status VARCHAR NOT NULL CHECK (status IN ('scheduled', 'completed', 'canceled')),
  escalated BOOLEAN DEFAULT FALSE,
  escalation_reason TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_appointment_schedule_mother_id ON appointment_schedule(mother_id);
CREATE INDEX idx_appointment_schedule_health_worker_id ON appointment_schedule(health_worker_id);
CREATE INDEX idx_appointment_schedule_status ON appointment_schedule(status);
