from app import db

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
    created_at    = db.Column(db.DateTime, nullable=False)

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
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)  # Who created this appointment
    created_at         = db.Column(db.DateTime, nullable=False)
    updated_at         = db.Column(db.DateTime, nullable=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    # Named backrefs to avoid conflict with other FK→users relationships
    mother_user        = db.relationship('User', foreign_keys=[mother_id],
                                         backref=db.backref('appointments_as_mother', lazy=True))
    hw_user            = db.relationship('User', foreign_keys=[health_worker_id],
                                         backref=db.backref('appointments_as_hw', lazy=True))
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

# Escalation model: CHW escalates a mother's case to a nurse
class Escalation(db.Model):
    __tablename__ = 'escalations'
    id               = db.Column(db.Integer, primary_key=True)
    chw_id           = db.Column(db.Integer, db.ForeignKey('chws.id', ondelete='CASCADE'), nullable=False)
    chw_name         = db.Column(db.String(128), nullable=False)
    nurse_id         = db.Column(db.Integer, db.ForeignKey('nurses.id', ondelete='CASCADE'), nullable=False)
    nurse_name       = db.Column(db.String(128), nullable=False)
    mother_id        = db.Column(db.Integer, db.ForeignKey('mothers.id', ondelete='CASCADE'))
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
    title = db.Column(db.String, nullable=False)
    content = db.Column(db.Text, nullable=False)
    target_group = db.Column(db.String)
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
