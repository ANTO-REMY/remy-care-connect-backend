-- 034_create_ultrasound_record.sql
-- Stores ultrasound scan measurements entered by CHW / Nurse

CREATE TABLE IF NOT EXISTS ultrasound_record (
    id SERIAL PRIMARY KEY,
    mother_id INTEGER NOT NULL REFERENCES mothers(id) ON DELETE CASCADE,
    week_number INTEGER NOT NULL,
    fetal_weight_grams NUMERIC(7,1),
    fetal_length_cm NUMERIC(5,1),
    heart_rate_bpm INTEGER,
    notes TEXT,
    recorded_by INTEGER NOT NULL REFERENCES users(id) ON DELETE SET NULL,
    scan_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ultrasound_mother ON ultrasound_record(mother_id);
