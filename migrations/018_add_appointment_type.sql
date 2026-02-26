-- Migration 018: Add appointment_type column to appointment_schedule table
ALTER TABLE appointment_schedule
  ADD COLUMN IF NOT EXISTS appointment_type VARCHAR(64);
