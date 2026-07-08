from app import db
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime, timedelta, timezone

# ── Administrative location models (Nairobi County) ──────────────────────────

class SubCounty(db.Model):
    __tablename__ = 'sub_counties'
    id   = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    wards = db.relationship('Ward', backref='sub_county', lazy=True)

class Ward(db.Model):
    __tablename__ = 'wards'
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(128), nullable=False)
    sub_county_id = db.Column(db.Integer, db.ForeignKey('sub_counties.id'), nullable=False)

# ── User models ───────────────────────────────────────────────────────────────

# User model: stores all users (mothers, CHWs, nurses) with authentication info
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), unique=True, nullable=False)
    first_name = db.Column(db.String(64), nullable=False)
    last_name  = db.Column(db.String(64), nullable=False, default='')
    email      = db.Column(db.String(255), nullable=True)
    pin_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(10), nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False)
    mother = db.relationship('Mother', backref='user', uselist=False)
    chw = db.relationship('CHW', backref='user', uselist=False)
    nurse = db.relationship('Nurse', backref='user', uselist=False)
    reminders = db.relationship('Reminder', backref='user', foreign_keys='Reminder.user_id', lazy=True, cascade='all, delete-orphan')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def name(self):
        """Full name — joins first_name and last_name. Read-only convenience property."""
        return f"{self.first_name} {self.last_name}".strip()

# UserSession model: stores active sessions for hybrid authentication
class UserSession(db.Model):
    __tablename__ = 'user_sessions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    session_token = db.Column(db.String(255), unique=True, nullable=False)
    device_info = db.Column(db.String(255))
    ip_address = db.Column(db.String(45))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    last_activity = db.Column(db.DateTime, nullable=False)
    user = db.relationship('User', backref='sessions')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

# Mother model: profile and demographic info for mothers, linked to User
class Mother(db.Model):
    __tablename__ = 'mothers'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    mother_name = db.Column(db.String(128), nullable=False)
    dob = db.Column(db.Date, nullable=False)       # filled during registration
    due_date = db.Column(db.Date, nullable=False)   # filled during registration
    location      = db.Column(db.String(128), nullable=True)   # derived from ward name
    ward_id       = db.Column(db.Integer, db.ForeignKey('wards.id'), nullable=False)
    sub_county_id = db.Column(db.Integer, db.ForeignKey('sub_counties.id'), nullable=False)
    created_at    = db.Column(db.DateTime, nullable=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

# CHW model: profile for community health workers, linked to User
class CHW(db.Model):
    __tablename__ = 'chws'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    chw_name = db.Column(db.String(128), nullable=False)
    license_number = db.Column(db.String(64), nullable=False)
    location      = db.Column(db.String(128), nullable=True)   # derived from ward name
    ward_id       = db.Column(db.Integer, db.ForeignKey('wards.id'), nullable=False)
    sub_county_id = db.Column(db.Integer, db.ForeignKey('sub_counties.id'), nullable=False)
    linked_facility_id = db.Column(db.Integer, db.ForeignKey('health_facilities.id', ondelete='SET NULL'))
    pending_facility_submission_id = db.Column(db.Integer, db.ForeignKey('chw_facility_submissions.id', ondelete='SET NULL'))
    created_at    = db.Column(db.DateTime, nullable=False)

    linked_facility = db.relationship('HealthFacility', foreign_keys=[linked_facility_id])
    pending_facility_submission = db.relationship(
        'CHWFacilitySubmission',
        foreign_keys=[pending_facility_submission_id],
        post_update=True,
    )

    @property
    def facility_link_status(self):
        if self.linked_facility_id:
            return 'approved'
        pending = self.pending_facility_submission
        if not pending:
            return 'not_linked'
        if pending.status == 'pending':
            return 'awaiting_approval'
        if pending.status == 'rejected':
            return 'rejected'
        if pending.status == 'approved' and pending.matched_health_facility_id:
            return 'approved'
        return 'not_linked'

    def facility_link_summary(self):
        pending = self.pending_facility_submission
        return {
            'facility_link_status': self.facility_link_status,
            'linked_facility_id': self.linked_facility_id,
            'linked_facility_name': self.linked_facility.name if self.linked_facility else None,
            'pending_facility_submission_id': pending.id if pending else None,
            'pending_facility_submission_status': pending.status if pending else None,
            'pending_facility_name': pending.facility_name if pending else None,
            'pending_facility_ward_id': pending.ward_id if pending else None,
            'pending_facility_ward_name': pending.ward.name if pending and pending.ward else None,
            'pending_facility_sub_county_id': pending.sub_county_id if pending else None,
            'pending_facility_sub_county_name': pending.sub_county.name if pending and pending.sub_county else None,
        }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

# Nurse model: profile for nurses, linked to User
class Nurse(db.Model):
    __tablename__ = 'nurses'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    nurse_name = db.Column(db.String(128), nullable=False)
    license_number = db.Column(db.String(64), nullable=False)
    location      = db.Column(db.String(128), nullable=True)   # derived from ward name
    ward_id       = db.Column(db.Integer, db.ForeignKey('wards.id'), nullable=False)
    sub_county_id = db.Column(db.Integer, db.ForeignKey('sub_counties.id'), nullable=False)
    created_at    = db.Column(db.DateTime, nullable=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

# Verification model: stores OTP codes for phone verification, linked to User if exists
class Verification(db.Model):
    __tablename__ = 'verifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    phone_number = db.Column(db.String(20), nullable=False)
    code = db.Column(db.String(5), nullable=False)
    status = db.Column(db.Enum('pending', 'verified', 'expired', name='verification_status'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)

# ProfilePhoto model: stores profile photo uploads per user; only one is active at a time
class ProfilePhoto(db.Model):
    __tablename__ = 'profile_photos'
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    role        = db.Column(db.Enum('mother', 'chw', 'nurse', name='user_roles'), nullable=False)
    file_name   = db.Column(db.String(255), nullable=False)   # sanitised original filename
    file_url    = db.Column(db.String(512), nullable=False)   # relative URL served by Flask
    mime_type   = db.Column(db.String(64), nullable=False, default='image/jpeg')
    file_size   = db.Column(db.Integer)                       # bytes
    is_active   = db.Column(db.Boolean, nullable=False, default=True)
    uploaded_at = db.Column(db.DateTime, nullable=False)
    updated_at  = db.Column(db.DateTime, nullable=False)
    user        = db.relationship('User', backref=db.backref('profile_photos', lazy=True))

# AppointmentSchedule model: recurring appointments and escalation
class AppointmentSchedule(db.Model):
    __tablename__ = 'appointment_schedule'
    id = db.Column(db.Integer, primary_key=True)
    # FK to users.id — both mother and health worker are users
    mother_id          = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    health_worker_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    scheduled_time     = db.Column(db.DateTime, nullable=False)
    recurrence_rule    = db.Column(db.String)
    recurrence_end     = db.Column(db.DateTime)
    status             = db.Column(db.Enum('scheduled', 'completed', 'canceled', name='appointment_status'), nullable=False)
    appointment_type   = db.Column(db.String(64))
    escalated          = db.Column(db.Boolean, default=False)
    escalation_reason  = db.Column(db.Text)
    notes              = db.Column(db.Text)
    ticket_code        = db.Column(db.String(32), unique=True, nullable=False)
    ticket_status      = db.Column(db.String(16), nullable=False, default='active')
    validated_at       = db.Column(db.DateTime(timezone=True))
    validated_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    validation_method  = db.Column(db.String(16))
    ticket_last_event_at = db.Column(db.DateTime(timezone=True))
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)  # Who created this appointment
    created_at         = db.Column(db.DateTime, nullable=False)
    updated_at         = db.Column(db.DateTime, nullable=False)

    __table_args__ = (
        db.CheckConstraint(
            "ticket_status IN ('active', 'used', 'canceled', 'expired')",
            name='chk_appointment_ticket_status'
        ),
        db.CheckConstraint(
            "validation_method IS NULL OR validation_method IN ('manual', 'qr', 'otp')",
            name='chk_appointment_validation_method'
        ),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    # Named backrefs to avoid conflict with other FK→users relationships
    mother_user        = db.relationship('User', foreign_keys=[mother_id],
                                         backref=db.backref('appointments_as_mother', lazy=True))
    hw_user            = db.relationship('User', foreign_keys=[health_worker_id],
                                         backref=db.backref('appointments_as_hw', lazy=True))
    validated_by_user  = db.relationship('User', foreign_keys=[validated_by_user_id],
                                         backref=db.backref('appointments_validated', lazy=True))
    creator_user       = db.relationship('User', foreign_keys=[created_by_user_id],
                                         backref=db.backref('appointments_created', lazy=True))


class AppointmentHiddenForUser(db.Model):
    __tablename__ = 'appointment_hidden_for_user'
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointment_schedule.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    hidden_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())
    reason = db.Column(db.Text)

    __table_args__ = (
        db.UniqueConstraint('appointment_id', 'user_id', name='uq_appointment_hidden_user'),
    )

    appointment = db.relationship('AppointmentSchedule', backref=db.backref('hidden_for_users', lazy=True, cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('hidden_appointments', lazy=True, cascade='all, delete-orphan'))


class AppointmentTicketEvent(db.Model):
    __tablename__ = 'appointment_ticket_events'

    id = db.Column(db.BigInteger, primary_key=True)
    appointment_source = db.Column(db.String(16), nullable=False)
    appointment_id = db.Column(db.Integer, nullable=False)
    ticket_code = db.Column(db.String(32), nullable=False)
    event_type = db.Column(db.String(32), nullable=False)
    actor_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    actor_facility_account_id = db.Column(db.Integer, db.ForeignKey('facility_accounts.id', ondelete='SET NULL'))
    actor_role = db.Column(db.String(32))
    event_time = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())
    metadata_json = db.Column(JSONB, nullable=False, server_default=db.text("'{}'::jsonb"))
    notes = db.Column(db.Text)

    __table_args__ = (
        db.CheckConstraint(
            "appointment_source IN ('standard', 'facility')",
            name='chk_appointment_ticket_event_source'
        ),
        db.CheckConstraint(
            "event_type IN ('generated', 'rescheduled', 'validated', 'canceled', 'expired', 'regenerated', 'duplicate_validation_attempt')",
            name='chk_appointment_ticket_event_type'
        ),
        db.CheckConstraint(
            "NOT (actor_user_id IS NOT NULL AND actor_facility_account_id IS NOT NULL)",
            name='chk_appointment_ticket_event_single_actor'
        ),
    )

    actor_user = db.relationship('User', foreign_keys=[actor_user_id])
    actor_facility_account = db.relationship('FacilityAccount', foreign_keys=[actor_facility_account_id])

# Escalation model: CHW escalates a mother's case to a nurse
class Escalation(db.Model):
    __tablename__ = 'escalations'
    id               = db.Column(db.Integer, primary_key=True)
    chw_id           = db.Column(db.Integer, db.ForeignKey('chws.id', ondelete='CASCADE'), nullable=False)
    chw_name         = db.Column(db.String(128), nullable=False)
    nurse_id         = db.Column(db.Integer, db.ForeignKey('nurses.id', ondelete='CASCADE'), nullable=False)
    nurse_name       = db.Column(db.String(128), nullable=False)
    mother_id        = db.Column(db.Integer, db.ForeignKey('mothers.id', ondelete='CASCADE'))
    checkin_id       = db.Column(db.Integer, db.ForeignKey('daily_checkin.id', ondelete='SET NULL'))
    mother_name      = db.Column(db.String(128), nullable=False)
    case_description = db.Column(db.Text, nullable=False)
    issue_type       = db.Column(db.String(64))
    notes            = db.Column(db.Text)
    priority         = db.Column(db.String(16), nullable=False, default='medium')
    status           = db.Column(db.String(16), nullable=False, default='pending')
    created_at       = db.Column(db.DateTime, nullable=False)
    resolved_at      = db.Column(db.DateTime)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('pending', 'in_progress', 'resolved', 'rejected')",
            name='chk_escalation_status'
        ),
        db.CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'critical')",
            name='chk_escalation_priority'
        ),
    )

    chw    = db.relationship('CHW',    backref=db.backref('escalations', lazy=True))
    nurse  = db.relationship('Nurse',  backref=db.backref('escalations_received', lazy=True))
    mother = db.relationship('Mother', backref=db.backref('escalations', lazy=True))
    checkin = db.relationship('DailyCheckin', backref=db.backref('escalations', lazy=True))


class EscalationHiddenForUser(db.Model):
    """Per-user soft-delete for escalations. Hiding is per-user — it never removes the source row."""
    __tablename__ = 'escalation_hidden_for_user'
    id = db.Column(db.Integer, primary_key=True)
    escalation_id = db.Column(db.Integer, db.ForeignKey('escalations.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    hidden_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())
    reason = db.Column(db.Text)

    __table_args__ = (
        db.UniqueConstraint('escalation_id', 'user_id', name='uq_escalation_hidden_user'),
    )

    escalation = db.relationship('Escalation', backref=db.backref('hidden_for_users', lazy=True, cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('hidden_escalations', lazy=True, cascade='all, delete-orphan'))

# DailyCheckin model: daily health status from mothers
class DailyCheckin(db.Model):
    __tablename__ = 'daily_checkin'
    id         = db.Column(db.Integer, primary_key=True)
    mother_id  = db.Column(db.Integer, db.ForeignKey('mothers.id', ondelete='CASCADE'), nullable=False)
    response   = db.Column(db.String, nullable=False)   # 'ok' | 'not_ok'
    comment    = db.Column(db.Text)
    symptoms   = db.Column(JSONB, nullable=False, server_default=db.text("'[]'::jsonb"))  # structured symptom list
    channel    = db.Column(db.String, nullable=False, default='app')  # 'app' | 'whatsapp' | 'sms'
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    mother = db.relationship('Mother', backref=db.backref('checkins', lazy=True))

class DailyCheckinHiddenForUser(db.Model):
    """Per-user soft-delete for daily check-ins."""
    __tablename__ = 'daily_checkin_hidden_for_user'
    id = db.Column(db.Integer, primary_key=True)
    checkin_id = db.Column(db.Integer, db.ForeignKey('daily_checkin.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    hidden_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())
    reason = db.Column(db.Text)

    __table_args__ = (
        db.UniqueConstraint('checkin_id', 'user_id', name='uq_daily_checkin_hidden_user'),
    )

    checkin = db.relationship('DailyCheckin', backref=db.backref('hidden_for_users', lazy=True, cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('hidden_checkins', lazy=True, cascade='all, delete-orphan'))

# MedicalRecordType model: extensible enum for record types
class MedicalRecordType(db.Model):
    __tablename__ = 'medical_record_type'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, unique=True, nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False)

# EducationalMaterial model: text or file uploads for CHW/nurse
class EducationalMaterial(db.Model):
    __tablename__ = 'educational_material'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    content = db.Column(db.Text)
    file_url = db.Column(db.String)
    category = db.Column(db.String)
    audience = db.Column(db.Enum('chw', 'nurse', 'both', name='educational_audience'), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False)

# DietaryRecommendation model: nutrition advice for mothers
class DietaryRecommendation(db.Model):
    __tablename__ = 'dietary_recommendation'
    id = db.Column(db.Integer, primary_key=True)
    source_id = db.Column(db.String(64), unique=True)
    title = db.Column(db.String, nullable=False)
    swahili_name = db.Column(db.String)
    content = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)
    target_group = db.Column(db.String)
    target_groups = db.Column(JSONB, nullable=False, server_default=db.text("'[]'::jsonb"))
    trimester_tags = db.Column(JSONB, nullable=False, server_default=db.text("'[]'::jsonb"))
    meal_type = db.Column(db.String(64))
    meal_time = db.Column(db.String(32))
    key_nutrients = db.Column(JSONB, nullable=False, server_default=db.text("'[]'::jsonb"))
    health_benefits = db.Column(JSONB, nullable=False, server_default=db.text("'[]'::jsonb"))
    preparation_tips = db.Column(db.Text)
    cautions = db.Column(JSONB, nullable=False, server_default=db.text("'[]'::jsonb"))
    nutrition_highlight = db.Column(db.String(255))
    portion_guide = db.Column(db.Text)
    image_suggestion = db.Column(db.String(255))
    tags = db.Column(JSONB, nullable=False, server_default=db.text("'[]'::jsonb"))
    calories = db.Column(db.Integer)
    is_featured = db.Column(db.Boolean, nullable=False, default=False)
    source_name = db.Column(db.String)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False)

# NextOfKin model: stores next of kin for mothers
class NextOfKin(db.Model):
    __tablename__ = 'next_of_kin'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('mothers.id'), nullable=False)
    mother_name = db.Column(db.String(128), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(32), nullable=False)
    sex = db.Column(db.String(8), nullable=False)
    relationship = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)

# DeviceToken model: stores Firebase Cloud Messaging tokens for push notifications
class DeviceToken(db.Model):
    __tablename__ = 'device_tokens'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    fcm_token = db.Column(db.String(255), nullable=False)
    device_info = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'fcm_token', name='uq_user_fcm_token'),
    )

    user = db.relationship('User', backref=db.backref('device_tokens', lazy=True, cascade='all, delete-orphan'))


# PushNotificationLog model: delivery telemetry for FCM sends
class PushNotificationLog(db.Model):
    __tablename__ = 'push_notification_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    event = db.Column(db.String(128), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=False)
    token_count = db.Column(db.Integer, nullable=False, default=0)
    success_count = db.Column(db.Integer, nullable=False, default=0)
    failure_count = db.Column(db.Integer, nullable=False, default=0)
    stale_token_count = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(32), nullable=False)
    error = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())

    user = db.relationship('User', backref=db.backref('push_notification_logs', lazy=True, cascade='all, delete-orphan'))


# UserNotification model: persistent in-app notification inbox per user
class UserNotification(db.Model):
    __tablename__ = 'user_notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    event_type = db.Column(db.String(128), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    url = db.Column(db.String(255))
    entity_type = db.Column(db.String(64))
    entity_id = db.Column(db.Integer)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    read_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())

    user = db.relationship('User', backref=db.backref('notifications', lazy=True, cascade='all, delete-orphan'))


# Resource model: educational materials and articles for role-specific content
class Resource(db.Model):
    __tablename__ = 'resources'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(100))
    target_role = db.Column(db.String(50), nullable=False)
    content_type = db.Column(db.String(50))
    url = db.Column(db.String(255))
    thumbnail = db.Column(db.String(255))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())

    __table_args__ = (
        db.CheckConstraint(
            "target_role IN ('mother', 'chw', 'nurse')",
            name='chk_resource_target_role'
        ),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


# WeightLog model: tracks mother's weight throughout pregnancy
class WeightLog(db.Model):
    __tablename__ = 'weight_log'
    id          = db.Column(db.Integer, primary_key=True)
    mother_id   = db.Column(db.Integer, db.ForeignKey('mothers.id', ondelete='CASCADE'), nullable=False)
    weight_kg   = db.Column(db.Numeric(5, 2), nullable=False)
    week_number = db.Column(db.Integer)
    notes       = db.Column(db.Text)
    recorded_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    created_at  = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())

    mother = db.relationship('Mother', backref=db.backref('weight_logs', lazy=True))
    recorder = db.relationship('User', foreign_keys=[recorded_by])


# UltrasoundRecord model: real fetal measurements from scans
class UltrasoundRecord(db.Model):
    __tablename__ = 'ultrasound_record'
    id                 = db.Column(db.Integer, primary_key=True)
    mother_id          = db.Column(db.Integer, db.ForeignKey('mothers.id', ondelete='CASCADE'), nullable=False)
    week_number        = db.Column(db.Integer, nullable=False)
    fetal_weight_grams = db.Column(db.Numeric(7, 1))
    fetal_length_cm    = db.Column(db.Numeric(5, 1))
    heart_rate_bpm     = db.Column(db.Integer)
    notes              = db.Column(db.Text)
    recorded_by        = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=False)
    scan_date          = db.Column(db.Date, nullable=False)
    created_at         = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())

    mother = db.relationship('Mother', backref=db.backref('ultrasound_records', lazy=True))
    recorder = db.relationship('User', foreign_keys=[recorded_by])


# Reminder model: persistent real-time reminders for mothers
class Reminder(db.Model):
    __tablename__ = 'reminders'
    id                 = db.Column(db.Integer, primary_key=True)
    user_id            = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    title              = db.Column(db.String(255), nullable=False)
    type               = db.Column(db.String(50), nullable=False)   # 'medication', 'hydration', 'exercise', etc.
    time_string        = db.Column(db.String(32), nullable=False)   # '8:00 AM', 'Anytime'
    frequency          = db.Column(db.String(50), nullable=False, default='daily') # 'daily', 'once'
    icon               = db.Column(db.String(32))                   # 'MED', 'H2O'
    last_completed_at  = db.Column(db.DateTime(timezone=True))
    created_at         = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())

    creator = db.relationship('User', foreign_keys=[created_by_user_id])


# ── Health Facilities Models ──────────────────────────────────────────────────

class FacilityAccount(db.Model):
    __tablename__ = 'facility_accounts'

    id = db.Column(db.Integer, primary_key=True)
    facility_id = db.Column(db.Integer, db.ForeignKey('health_facilities.id', ondelete='CASCADE'), nullable=False)
    phone_number = db.Column(db.String(20), unique=True)
    email = db.Column(db.String(100), unique=True)
    first_name = db.Column(db.String(64), nullable=False)
    last_name = db.Column(db.String(64), nullable=False, default='')
    pin_hash = db.Column(db.String(128))
    role = db.Column(db.String(50), nullable=False)  # admin, doctor, midwife, nurse, chw, receptionist
    profile_completed = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    facility = db.relationship('HealthFacility', foreign_keys=[facility_id], backref=db.backref('facility_accounts', lazy=True, cascade='all, delete-orphan'))

    @property
    def name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def to_dict(self):
        return {
            'id': self.id,
            'facility_id': self.facility_id,
            'phone_number': self.phone_number,
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'name': self.name,
            'role': self.role,
            'profile_completed': bool(self.profile_completed),
            'is_active': bool(self.is_active),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

# HealthFacility model: Kenya health facilities from OpenStreetMap dataset
class HealthFacility(db.Model):
    __tablename__ = 'health_facilities'
    
    id = db.Column(db.Integer, primary_key=True)
    osm_id = db.Column(db.BigInteger, unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    
    # Facility type classification
    amenity = db.Column(db.String(50))                                # pharmacy, clinic, hospital, dentist
    healthcare = db.Column(db.String(255))                            # clinic, pharmacy, hospital, laboratory (semicolon-separated)
    healthcare_specialities = db.Column(db.ARRAY(db.String), default=[])  # maternity, gynaecology
    operator_type = db.Column(db.String(50))                     # private, government, religious, ngo
    
    # Location information
    city = db.Column(db.String(100))
    address = db.Column(db.Text)
    geometry = db.Column(db.String)  # PostGIS GEOGRAPHY(POINT, 4326) - stored as WKT string

    # Inferred administrative mapping for facilities with incomplete source metadata
    inferred_ward_id = db.Column(db.Integer, db.ForeignKey('wards.id', ondelete='SET NULL'))
    inferred_sub_county_id = db.Column(db.Integer, db.ForeignKey('sub_counties.id', ondelete='SET NULL'))
    inference_source = db.Column(db.String(32), nullable=False, default='none')
    inference_confidence = db.Column(db.Float)
    location_quality_status = db.Column(db.String(16), nullable=False, default='unknown')

    # Persisted administrative names from one-time polygon enrichment.
    subcounty_name = db.Column(db.String(128))
    ward_name = db.Column(db.String(128))
    location_match_status = db.Column(db.String(32), nullable=False, default='manual_review')
    location_match_method = db.Column(db.String(64))
    location_matched_at = db.Column(db.DateTime)

    # County scope flags to quickly separate Nairobi facilities from the national dataset
    is_in_nairobi = db.Column(db.Boolean, nullable=False, default=False)
    nairobi_scope_source = db.Column(db.String(32), nullable=False, default='unset')
    near_nairobi_boundary = db.Column(db.Boolean, nullable=False, default=False)
    nairobi_boundary_distance_m = db.Column(db.Float)
    
    # Verification status
    verified = db.Column(db.Boolean, default=False)
    verified_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    verified_at = db.Column(db.DateTime)

    # Milestone 3: self-claim + facility admin ownership
    facility_admin_id = db.Column(db.Integer, db.ForeignKey('facility_accounts.id'))
    admin_verified_at = db.Column(db.DateTime)

    # Optional contact details managed by facility admin
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    hours_text = db.Column(db.Text)
    
    # Extensible facility metadata (renamed from 'metadata' to avoid SQLAlchemy reserved name)
    facility_metadata = db.Column(JSONB, default=dict)
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), 
                          onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    verifier = db.relationship('User', foreign_keys=[verified_by])
    admin = db.relationship('FacilityAccount', foreign_keys=[facility_admin_id])
    inferred_ward = db.relationship('Ward', foreign_keys=[inferred_ward_id])
    inferred_sub_county = db.relationship('SubCounty', foreign_keys=[inferred_sub_county_id])
    issues = db.relationship('FacilityIssue', back_populates='facility', lazy=True, cascade='all, delete-orphan')
    staff_memberships = db.relationship('FacilityStaff', backref='facility_obj', lazy=True, cascade='all, delete-orphan')
    invitations = db.relationship('FacilityInvitation', backref='facility_obj', lazy=True, cascade='all, delete-orphan')
    chw_submission_matches = db.relationship(
        'CHWFacilitySubmission',
        foreign_keys='CHWFacilitySubmission.matched_health_facility_id',
        back_populates='matched_health_facility',
        lazy=True,
    )
    
    def to_dict(self):
        """Serialize facility to dictionary"""
        # Parse geometry from WKT format: SRID=4326;POINT(lng lat)
        coords = {'lat': None, 'lng': None}
        if self.geometry:
            try:
                # Extract coordinates from WKT string
                import re
                match = re.search(r'POINT\(([^ ]+) ([^ ]+)\)', self.geometry)
                if match:
                    coords = {
                        'lng': float(match.group(1)),
                        'lat': float(match.group(2))
                    }
            except Exception:
                pass
        
        return {
            'id': self.id,
            'osm_id': self.osm_id,
            'name': self.name,
            'amenity': self.amenity,
            'healthcare': self.healthcare,
            'specialities': self.healthcare_specialities or [],
            'operator_type': self.operator_type,
            'city': self.city,
            'address': self.address,
            'verified': self.verified,
            'facility_admin_id': self.facility_admin_id,
            'coordinates': coords,
            'inferred_ward_id': self.inferred_ward_id,
            'inferred_sub_county_id': self.inferred_sub_county_id,
            'inference_source': self.inference_source,
            'inference_confidence': self.inference_confidence,
            'location_quality_status': self.location_quality_status,
            'subcounty_name': self.subcounty_name,
            'ward_name': self.ward_name,
            'location_match_status': self.location_match_status,
            'location_match_method': self.location_match_method,
            'location_matched_at': self.location_matched_at.isoformat() if self.location_matched_at else None,
            'metadata': self.facility_metadata or {},
            'phone': self.phone,
            'email': self.email,
            'hours_text': self.hours_text,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class CHWFacilitySubmission(db.Model):
    __tablename__ = 'chw_facility_submissions'

    id = db.Column(db.Integer, primary_key=True)
    submitted_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    chw_id = db.Column(db.Integer, db.ForeignKey('chws.id', ondelete='SET NULL'))
    facility_name = db.Column(db.String(255), nullable=False)
    normalized_facility_name = db.Column(db.String(255), nullable=False)
    ward_id = db.Column(db.Integer, db.ForeignKey('wards.id', ondelete='RESTRICT'), nullable=False)
    sub_county_id = db.Column(db.Integer, db.ForeignKey('sub_counties.id', ondelete='RESTRICT'), nullable=False)
    status = db.Column(db.String(32), nullable=False, default='pending')
    matched_health_facility_id = db.Column(db.Integer, db.ForeignKey('health_facilities.id', ondelete='SET NULL'))
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name='chk_chw_facility_submission_status',
        ),
    )

    submitter = db.relationship(
        'User',
        foreign_keys=[submitted_by_user_id],
        backref=db.backref('chw_facility_submissions', lazy=True, cascade='all, delete-orphan'),
    )
    chw = db.relationship(
        'CHW',
        foreign_keys=[chw_id],
        backref=db.backref('facility_submissions', lazy=True),
    )
    ward = db.relationship('Ward', foreign_keys=[ward_id])
    sub_county = db.relationship('SubCounty', foreign_keys=[sub_county_id])
    matched_health_facility = db.relationship(
        'HealthFacility',
        foreign_keys=[matched_health_facility_id],
        back_populates='chw_submission_matches',
    )

    def to_dict(self):
        return {
            'id': self.id,
            'submitted_by_user_id': self.submitted_by_user_id,
            'chw_id': self.chw_id,
            'facility_name': self.facility_name,
            'normalized_facility_name': self.normalized_facility_name,
            'ward_id': self.ward_id,
            'ward_name': self.ward.name if self.ward else None,
            'sub_county_id': self.sub_county_id,
            'sub_county_name': self.sub_county.name if self.sub_county else None,
            'status': self.status,
            'matched_health_facility_id': self.matched_health_facility_id,
            'matched_health_facility_name': self.matched_health_facility.name if self.matched_health_facility else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class OTPToken(db.Model):
    __tablename__ = 'otp_tokens'

    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20))
    email = db.Column(db.String(100))
    otp_code = db.Column(db.String(6), nullable=False)
    purpose = db.Column(db.String(50), nullable=False, default='facility_login')
    facility_id = db.Column(db.Integer, db.ForeignKey('health_facilities.id'))
    attempts = db.Column(db.Integer, nullable=False, default=0)
    max_attempts = db.Column(db.Integer, nullable=False, default=3)
    is_used = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc) + timedelta(minutes=15))
    used_at = db.Column(db.DateTime)

    facility = db.relationship('HealthFacility', backref=db.backref('otp_tokens', lazy=True))

    def is_valid(self):
        expires_at = self.expires_at
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return (
            (not self.is_used)
            and (self.attempts < self.max_attempts)
            and (expires_at is not None)
            and (datetime.now(timezone.utc) < expires_at)
        )


class FacilityStaff(db.Model):
    __tablename__ = 'facility_staff'

    id = db.Column(db.Integer, primary_key=True)
    facility_id = db.Column(db.Integer, db.ForeignKey('health_facilities.id', ondelete='CASCADE'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('facility_accounts.id', ondelete='CASCADE'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    invitation_id = db.Column(db.Integer, db.ForeignKey('facility_invitations.id', ondelete='SET NULL'))
    invitation_phone = db.Column(db.String(20))
    first_name = db.Column(db.String(64))
    last_name = db.Column(db.String(64), nullable=False, default='')
    role = db.Column(db.String(50), nullable=False)  # admin, doctor, midwife, nurse, chw, receptionist
    specialty = db.Column(db.String(120))
    status = db.Column(db.String(50), nullable=False, default='pending_verification')  # pending_verification, active, inactive, removed
    is_verified = db.Column(db.Boolean, nullable=False, default=False)
    verified_at = db.Column(db.DateTime)
    added_by_account_id = db.Column(db.Integer, db.ForeignKey('facility_accounts.id'))
    added_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('facility_id', 'account_id', name='uq_facility_staff_facility_account'),
    )

    account = db.relationship('FacilityAccount', foreign_keys=[account_id], backref=db.backref('facility_memberships', lazy=True))
    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('facility_staff_memberships', lazy=True))
    adder = db.relationship('FacilityAccount', foreign_keys=[added_by_account_id])
    invitation = db.relationship('FacilityInvitation', foreign_keys=[invitation_id])

    @property
    def display_name(self):
        if self.first_name or self.last_name:
            return f"{self.first_name or ''} {self.last_name or ''}".strip()
        if self.account and not self.account.profile_completed:
            return 'Pending profile'
        if self.status == 'pending_verification':
            return 'Pending profile'
        if self.account:
            return self.account.name
        if self.user:
            return self.user.name
        return None

    def to_dict(self):
        return {
            'id': self.id,
            'facility_id': self.facility_id,
            'account_id': self.account_id,
            'user_id': self.user_id,
            'invitation_id': self.invitation_id,
            'user_name': self.display_name,
            'first_name': self.first_name or (self.account.first_name if self.account else None),
            'last_name': self.last_name or (self.account.last_name if self.account else None),
            'phone_number': self.invitation_phone or (self.account.phone_number if self.account else None),
            'role': self.role,
            'specialty': self.specialty,
            'status': self.status,
            'is_verified': bool(self.is_verified),
            'verified_at': self.verified_at.isoformat() if self.verified_at else None,
            'added_by': self.added_by_account_id,
            'added_at': self.added_at.isoformat() if self.added_at else None,
        }


class FacilityInvitation(db.Model):
    __tablename__ = 'facility_invitations'

    id = db.Column(db.Integer, primary_key=True)
    facility_id = db.Column(db.Integer, db.ForeignKey('health_facilities.id', ondelete='CASCADE'), nullable=False)
    invitation_phone = db.Column(db.String(20))
    invitation_email = db.Column(db.String(100))
    invited_role = db.Column(db.String(50), nullable=False)
    invited_by = db.Column(db.Integer, db.ForeignKey('facility_accounts.id', ondelete='CASCADE'), nullable=False)
    status = db.Column(db.String(50), nullable=False, default='pending')  # pending, accepted, expired
    otp_id = db.Column(db.Integer, db.ForeignKey('otp_tokens.id'))
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc) + timedelta(days=7))
    accepted_at = db.Column(db.DateTime)

    inviter = db.relationship('FacilityAccount', foreign_keys=[invited_by])
    otp_token = db.relationship('OTPToken', foreign_keys=[otp_id])

    def is_active(self):
        expires_at = self.expires_at
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return (
            self.status == 'pending'
            and expires_at is not None
            and datetime.now(timezone.utc) < expires_at
        )


class FacilityAppointment(db.Model):
    __tablename__ = 'facility_appointments'

    id = db.Column(db.Integer, primary_key=True)
    facility_id = db.Column(db.Integer, db.ForeignKey('health_facilities.id', ondelete='CASCADE'), nullable=False)
    mother_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    mother_name = db.Column(db.String(128), nullable=False)
    scheduled_time = db.Column(db.DateTime, nullable=False)
    appointment_type = db.Column(db.String(64))
    status = db.Column(db.String(32), nullable=False, default='scheduled')
    assigned_staff_account_id = db.Column(db.Integer, db.ForeignKey('facility_accounts.id', ondelete='SET NULL'))
    created_by_account_id = db.Column(db.Integer, db.ForeignKey('facility_accounts.id', ondelete='SET NULL'))
    notes = db.Column(db.Text)
    mother_response_status = db.Column(db.String(16))
    mother_response_note = db.Column(db.Text)
    mother_responded_at = db.Column(db.DateTime(timezone=True))
    ticket_code = db.Column(db.String(32), unique=True, nullable=False)
    ticket_status = db.Column(db.String(16), nullable=False, default='active')
    validated_at = db.Column(db.DateTime(timezone=True))
    validated_by_account_id = db.Column(db.Integer, db.ForeignKey('facility_accounts.id', ondelete='SET NULL'))
    validation_method = db.Column(db.String(16))
    ticket_last_event_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            "ticket_status IN ('active', 'used', 'canceled', 'expired')",
            name='chk_facility_appointment_ticket_status'
        ),
        db.CheckConstraint(
            "validation_method IS NULL OR validation_method IN ('manual', 'qr', 'otp')",
            name='chk_facility_appointment_validation_method'
        ),
    )

    facility = db.relationship('HealthFacility', foreign_keys=[facility_id], backref=db.backref('facility_appointments', lazy=True, cascade='all, delete-orphan'))
    mother_user = db.relationship('User', foreign_keys=[mother_id])
    assigned_staff = db.relationship('FacilityAccount', foreign_keys=[assigned_staff_account_id])
    creator_account = db.relationship('FacilityAccount', foreign_keys=[created_by_account_id])
    validated_by_account = db.relationship('FacilityAccount', foreign_keys=[validated_by_account_id])

    def to_dict(self):
        return {
            'id': self.id,
            'facility_id': self.facility_id,
            'mother_id': self.mother_id,
            'mother_name': self.mother_name,
            'scheduled_time': self.scheduled_time.isoformat() if self.scheduled_time else None,
            'appointment_type': self.appointment_type,
            'status': self.status,
            'assigned_staff_account_id': self.assigned_staff_account_id,
            'assigned_staff_name': self.assigned_staff.name if self.assigned_staff else None,
            'created_by_account_id': self.created_by_account_id,
            'notes': self.notes,
            'mother_response_status': self.mother_response_status,
            'mother_response_note': self.mother_response_note,
            'mother_responded_at': self.mother_responded_at.isoformat() if self.mother_responded_at else None,
            'ticket_code': self.ticket_code,
            'ticket_status': self.ticket_status,
            'validated_at': self.validated_at.isoformat() if self.validated_at else None,
            'validated_by_account_id': self.validated_by_account_id,
            'validation_method': self.validation_method,
            'ticket_last_event_at': self.ticket_last_event_at.isoformat() if self.ticket_last_event_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class FacilityEscalation(db.Model):
    __tablename__ = 'facility_escalations'

    id = db.Column(db.Integer, primary_key=True)
    facility_id = db.Column(db.Integer, db.ForeignKey('health_facilities.id', ondelete='CASCADE'), nullable=False)
    mother_id = db.Column(db.Integer, db.ForeignKey('mothers.id', ondelete='SET NULL'))
    mother_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    mother_name = db.Column(db.String(128), nullable=False)
    chw_id = db.Column(db.Integer, db.ForeignKey('chws.id', ondelete='SET NULL'))
    chw_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    checkin_id = db.Column(db.Integer, db.ForeignKey('daily_checkin.id', ondelete='SET NULL'))
    case_description = db.Column(db.Text, nullable=False)
    issue_type = db.Column(db.String(64))
    notes = db.Column(db.Text)
    priority = db.Column(db.String(16), nullable=False, default='medium')
    status = db.Column(db.String(20), nullable=False, default='received')
    assigned_staff_account_id = db.Column(db.Integer, db.ForeignKey('facility_accounts.id', ondelete='SET NULL'))
    assigned_staff_role = db.Column(db.String(20))
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    updated_by_account_id = db.Column(db.Integer, db.ForeignKey('facility_accounts.id', ondelete='SET NULL'))
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    checked_out_at = db.Column(db.DateTime)

    __table_args__ = (
        db.CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'critical')",
            name='chk_facility_escalations_priority',
        ),
        db.CheckConstraint(
            "status IN ('received', 'in_progress', 'checked_out')",
            name='chk_facility_escalations_status',
        ),
    )

    facility = db.relationship('HealthFacility', foreign_keys=[facility_id], backref=db.backref('facility_escalations', lazy=True, cascade='all, delete-orphan'))
    mother = db.relationship('Mother', foreign_keys=[mother_id])
    mother_user = db.relationship('User', foreign_keys=[mother_user_id], backref=db.backref('facility_escalations_as_mother', lazy=True))
    chw = db.relationship('CHW', foreign_keys=[chw_id])
    chw_user = db.relationship('User', foreign_keys=[chw_user_id], backref=db.backref('facility_escalations_as_chw', lazy=True))
    checkin = db.relationship('DailyCheckin', foreign_keys=[checkin_id])
    assigned_staff = db.relationship('FacilityAccount', foreign_keys=[assigned_staff_account_id])
    creator_user = db.relationship('User', foreign_keys=[created_by_user_id])
    updater_account = db.relationship('FacilityAccount', foreign_keys=[updated_by_account_id])

    def to_dict(self):
        facility_name = self.facility.name if self.facility else None
        facility_phone = self.facility.phone if self.facility else None
        facility_city = self.facility.city if self.facility else None
        facility_address = self.facility.address if self.facility else None

        return {
            'id': self.id,
            'facility_id': self.facility_id,
            'facility_name': facility_name,
            'facility_phone': facility_phone,
            'facility_city': facility_city,
            'facility_address': facility_address,
            'mother_id': self.mother_id,
            'mother_user_id': self.mother_user_id,
            'mother_name': self.mother_name,
            'chw_id': self.chw_id,
            'chw_user_id': self.chw_user_id,
            'checkin_id': self.checkin_id,
            'case_description': self.case_description,
            'issue_type': self.issue_type,
            'notes': self.notes,
            'priority': self.priority,
            'status': self.status,
            'assigned_staff_account_id': self.assigned_staff_account_id,
            'assigned_staff_name': self.assigned_staff.name if self.assigned_staff else None,
            'assigned_staff_role': self.assigned_staff_role,
            'created_by_user_id': self.created_by_user_id,
            'updated_by_account_id': self.updated_by_account_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'checked_out_at': self.checked_out_at.isoformat() if self.checked_out_at else None,
        }


# FacilityIssue model: user-reported problems with health facilities
class FacilityIssue(db.Model):
    __tablename__ = 'facility_issues'
    
    id = db.Column(db.Integer, primary_key=True)
    facility_id = db.Column(db.Integer, db.ForeignKey('health_facilities.id', ondelete='CASCADE'), nullable=False)
    reported_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    
    # Issue classification
    issue_type = db.Column(db.String(50), nullable=False)  # closed, wrong_location, wrong_name, wrong_info, other
    description = db.Column(db.Text)
    
    # Issue lifecycle
    status = db.Column(db.String(50), nullable=False, default='reported')  # reported, acknowledged, in_progress, resolved, rejected
    priority = db.Column(db.String(20), default='medium')  # low, medium, high
    
    # Resolution tracking
    resolved_at = db.Column(db.DateTime)
    resolved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    resolution_notes = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), 
                          onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    facility = db.relationship('HealthFacility', foreign_keys=[facility_id], back_populates='issues')
    reporter = db.relationship('User', foreign_keys=[reported_by], backref=db.backref('reported_facility_issues', lazy=True))
    resolver = db.relationship('User', foreign_keys=[resolved_by])
    
    def to_dict(self):
        """Serialize issue to dictionary"""
        try:
            facility_name = self.facility.name if self.facility else None
        except Exception:
            # Relationship might be unavailable outside session context
            facility_name = None

        try:
            reporter_name = f"{self.reporter.first_name} {self.reporter.last_name}" if self.reporter else None
        except Exception:
            reporter_name = None

        return {
            'id': self.id,
            'facility_id': self.facility_id,
            'facility_name': facility_name,
            'reported_by': self.reported_by,
            'reporter_name': reporter_name,
            'issue_type': self.issue_type,
            'description': self.description,
            'status': self.status,
            'priority': self.priority,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'resolution_notes': self.resolution_notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
