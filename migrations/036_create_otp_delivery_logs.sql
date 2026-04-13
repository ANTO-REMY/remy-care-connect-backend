-- Migration 036: Create OTP delivery logs table for audit and troubleshooting
CREATE TABLE otp_delivery_logs (
    id SERIAL PRIMARY KEY,
    phone_number VARCHAR(20) NOT NULL,
    method VARCHAR(20) NOT NULL CHECK (method IN ('sms', 'whatsapp', 'console')),
    success BOOLEAN NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX idx_otp_delivery_logs_phone_created_at
    ON otp_delivery_logs (phone_number, created_at DESC);

CREATE INDEX idx_otp_delivery_logs_success_created_at
    ON otp_delivery_logs (success, created_at DESC);

