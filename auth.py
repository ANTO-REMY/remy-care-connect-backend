from flask import Blueprint, request, jsonify, session
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity
from models import db, User, Verification, Mother, CHW, Nurse, Ward, FacilityAccount, FacilityStaff, OTPToken, HealthFacility, CHWFacilitySubmission
from auth_utils import (
    generate_otp, hash_pin, verify_pin, create_user_session, 
    validate_session_token, require_auth, get_current_user, logout_user_sessions
)
from assignment_utils import (
    ASSIGNMENT_METHOD_AUTO_WARD_MATCH,
    assign_mother_if_possible,
    backfill_chw_from_ward_backlog,
    emit_assignment_event,
)
from datetime import datetime, timedelta, timezone
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, func
import random
import re
import json
import logging
from africas_talking_service import send_otp, get_otp_service

bp = Blueprint('auth', __name__)
log = logging.getLogger(__name__)

def normalize_phone_number(phone):
    """Normalize phone number from 07xxxxxxxx to +254xxxxxxxx format"""
    # Remove all spaces and special characters
    phone = (phone or '').strip()
    cleaned = re.sub(r'[^0-9]', '', phone)
    
    # Only handle 07xxxxxxxx format
    if cleaned.startswith('07') and len(cleaned) == 10:
        # Convert 07xxxxxxxx to +254xxxxxxxx
        return '+254' + cleaned[1:]

    # Handle 254xxxxxxxxx format (no plus)
    if cleaned.startswith('254') and len(cleaned) == 12:
        return '+' + cleaned

    # Keep already-normalized +254xxxxxxxxx values
    if phone.startswith('+254') and len(re.sub(r'[^0-9]', '', phone)) == 12:
        return '+254' + re.sub(r'[^0-9]', '', phone)[3:]
    
    # Return as-is if not in expected format (will fail validation)
    return phone

def validate_phone_number(phone):
    """Validate Kenyan phone number in 07xxxxxxxx, 254xxxxxxxxx, or +254xxxxxxxxx formats."""
    # Remove all spaces and special characters
    cleaned = re.sub(r'[^0-9+]', '', phone)
    
    # Check if it's 07xxxxxxxx format
    if re.match(r'^07[0-9]{8}$', cleaned):
        return True
    
    # Also temporarily accept +254xxxxxxx format for existing users
    if re.match(r'^\+254[0-9]{9}$', cleaned):
        return True

    # Also accept 254xxxxxxxxx format (without plus)
    if re.match(r'^254[0-9]{9}$', cleaned):
        return True
    
    return False


def phone_lookup_candidates(phone):
    """Return normalized lookup variants so legacy-stored numbers are still discoverable."""
    normalized = normalize_phone_number(phone)
    digits = re.sub(r'[^0-9]', '', phone or '')
    candidates = []

    def _add(value):
        if value and value not in candidates:
            candidates.append(value)

    _add(normalized)

    # Canonical variants
    if normalized.startswith('+254') and len(re.sub(r'[^0-9]', '', normalized)) == 12:
        _add(normalized[1:])
        _add('0' + normalized[4:])
    elif normalized.startswith('254') and len(normalized) == 12:
        _add('+' + normalized)
        _add('0' + normalized[3:])
    elif normalized.startswith('07') and len(normalized) == 10:
        _add('+254' + normalized[1:])
        _add('254' + normalized[1:])

    # Raw cleaned input as fallback
    if digits.startswith('254') and len(digits) == 12:
        _add('+' + digits)
        _add('0' + digits[3:])
    elif digits.startswith('07') and len(digits) == 10:
        _add('+254' + digits[1:])
        _add('254' + digits[1:])

    return candidates


def _find_user_by_contact(phone_number=None, email=None):
    """Resolve a user by phone variants and/or email with best-effort matching."""
    email_normalized = (email or '').strip().lower() or None

    if phone_number:
        candidates = phone_lookup_candidates(phone_number)
        users = User.query.filter(User.phone_number.in_(candidates)).all()
        if email_normalized:
            for row in users:
                if (row.email or '').strip().lower() == email_normalized:
                    return row
        if users:
            return users[0]

    if email_normalized:
        users = User.query.all()
        for row in users:
            if (row.email or '').strip().lower() == email_normalized:
                return row

    return None


def _find_facility_account_by_contact(phone_number=None, email=None):
    """Resolve a facility account by phone variants and/or email with best-effort matching."""
    email_normalized = (email or '').strip().lower() or None

    if phone_number:
        candidates = phone_lookup_candidates(phone_number)
        accounts = FacilityAccount.query.filter(FacilityAccount.phone_number.in_(candidates)).all()
        if email_normalized:
            for row in accounts:
                if (row.email or '').strip().lower() == email_normalized:
                    return row
        if accounts:
            return accounts[0]

    if email_normalized:
        accounts = FacilityAccount.query.all()
        for row in accounts:
            if (row.email or '').strip().lower() == email_normalized:
                return row

    return None


def _resolve_login_subject(user, facility_account, pin, role_hint=None):
    """
    Determine which identity should authenticate for /auth/login.

    Resolution order:
      1) Explicit role_hint (if provided and credentials match).
      2) Unique successful PIN match.
      3) If both PINs match, prefer verified app user unless hint says facility.
    """
    hint = (role_hint or '').strip().lower()

    user_pin_ok = bool(user and user.pin_hash and verify_pin(pin, user.pin_hash))
    facility_pin_ok = bool(facility_account and facility_account.pin_hash and verify_pin(pin, facility_account.pin_hash))

    if hint in {'facility', 'facility_staff', 'facility_account', 'admin', 'doctor', 'nurse'}:
        if facility_pin_ok:
            return 'facility', user_pin_ok, facility_pin_ok
        if user_pin_ok:
            return 'user', user_pin_ok, facility_pin_ok

    if hint in {'user', 'mother', 'chw'}:
        if user_pin_ok:
            return 'user', user_pin_ok, facility_pin_ok
        if facility_pin_ok:
            return 'facility', user_pin_ok, facility_pin_ok

    if user_pin_ok and not facility_pin_ok:
        return 'user', user_pin_ok, facility_pin_ok
    if facility_pin_ok and not user_pin_ok:
        return 'facility', user_pin_ok, facility_pin_ok

    if user_pin_ok and facility_pin_ok:
        if hint in {'facility', 'facility_staff', 'facility_account', 'admin', 'doctor', 'nurse'}:
            return 'facility', user_pin_ok, facility_pin_ok
        if hint in {'user', 'mother', 'chw'}:
            return 'user', user_pin_ok, facility_pin_ok
        if user and user.is_verified:
            return 'user', user_pin_ok, facility_pin_ok
        return 'facility', user_pin_ok, facility_pin_ok

    return None, user_pin_ok, facility_pin_ok


def _resolve_pin_reset_subject(phone_number, role_hint=None):
    hint = (role_hint or '').strip().lower()

    user = _find_user_by_contact(phone_number=phone_number)
    facility_account = _find_facility_account_by_contact(phone_number=phone_number)

    if hint in {'facility', 'facility_staff', 'facility_account', 'admin', 'doctor', 'nurse'}:
        if facility_account:
            return 'facility', facility_account
        if user:
            return 'user', user

    if hint in {'mother', 'chw', 'user'}:
        if user:
            return 'user', user
        if facility_account:
            return 'facility', facility_account

    if user:
        return 'user', user
    if facility_account:
        return 'facility', facility_account

    return None, None


def _parse_ward_or_error(ward_id_raw):
    try:
        ward_id = int(ward_id_raw)
    except (TypeError, ValueError):
        return None, (jsonify({'error': 'ward_id must be an integer'}), 400)

    ward = Ward.query.get(ward_id)
    if not ward:
        return None, (jsonify({'error': f'Ward with id {ward_id} not found'}), 400)

    return ward, None


def _normalize_facility_name(name: str | None):
    return re.sub(r'\s+', ' ', (name or '').strip()).lower()


def _facility_matches_ward_scope(facility: HealthFacility, ward: Ward):
    if not facility or not ward:
        return False

    if facility.inferred_ward_id == ward.id:
        return True

    if facility.inferred_sub_county_id == ward.sub_county_id:
        return True

    city = (facility.city or '').strip().lower()
    sub_county_name = (ward.sub_county.name if ward.sub_county else '') or ''
    sub_county_name = sub_county_name.strip().lower()

    if sub_county_name and sub_county_name in city:
        return True

    # Nairobi wards are often recorded under generic Nairobi city labels.
    if ward.sub_county and 'nairobi' in (ward.sub_county.name or '').lower() and 'nairobi' in city:
        return True

    return False


def _resolve_linked_facility_or_error(linked_facility_id_raw, ward: Ward):
    if linked_facility_id_raw in (None, ''):
        return None, None

    try:
        linked_facility_id = int(linked_facility_id_raw)
    except (TypeError, ValueError):
        return None, (jsonify({'error': 'linked_facility_id must be an integer'}), 400)

    linked_facility = HealthFacility.query.get(linked_facility_id)
    if not linked_facility:
        return None, (jsonify({'error': 'Selected linked facility was not found'}), 404)

    if not _facility_matches_ward_scope(linked_facility, ward):
        return None, (jsonify({'error': 'Selected linked facility must be within the selected sub-county'}), 400)

    return linked_facility, None


def _find_existing_subcounty_facility_by_name(normalized_name: str, ward: Ward):
    if not normalized_name or not ward:
        return None

    sub_county_name = (ward.sub_county.name if ward.sub_county else '') or ''
    query = (
        HealthFacility.query
        .filter(HealthFacility.name.isnot(None))
        .filter(func.length(func.trim(HealthFacility.name)) > 0)
        .filter(
            or_(
                HealthFacility.inferred_sub_county_id == ward.sub_county_id,
                HealthFacility.subcounty_name.ilike(sub_county_name) if sub_county_name else False,
                HealthFacility.city.ilike(f'%{sub_county_name}%') if sub_county_name else False,
            )
        )
    )

    for facility in query.order_by(HealthFacility.verified.desc(), HealthFacility.name).limit(200).all():
        if _normalize_facility_name(facility.name) == normalized_name:
            return facility

    return None


def _resolve_chw_facility_selection_or_error(data, ward: Ward):
    linked_facility_id = data.get('linked_facility_id')
    new_facility_name = (data.get('new_facility_name') or '').strip()
    new_facility_ward_id = data.get('new_facility_ward_id')

    if linked_facility_id not in (None, '') and new_facility_name:
        return None, None, (
            jsonify({'error': 'Provide either linked_facility_id or new_facility_name, not both'}),
            400,
        )

    linked_facility, linked_facility_error = _resolve_linked_facility_or_error(linked_facility_id, ward)
    if linked_facility_error:
        return None, None, linked_facility_error

    if not new_facility_name:
        return linked_facility, None, None

    submission_ward = ward
    if new_facility_ward_id not in (None, ''):
        submission_ward, submission_ward_error = _parse_ward_or_error(new_facility_ward_id)
        if submission_ward_error:
            return None, None, submission_ward_error
        if submission_ward.sub_county_id != ward.sub_county_id:
            return None, None, (
                jsonify({'error': 'New facility ward must be within the selected sub-county'}),
                400,
            )

    normalized_name = _normalize_facility_name(new_facility_name)
    if not normalized_name:
        return None, None, (jsonify({'error': 'new_facility_name cannot be blank'}), 400)

    existing_match = _find_existing_subcounty_facility_by_name(normalized_name, ward)
    if existing_match:
        return None, None, (
            jsonify({
                'error': 'Facility already exists in the selected sub-county. Please select the existing facility instead.',
                'existing_facility': {
                    'id': existing_match.id,
                    'name': existing_match.name,
                },
            }),
            409,
        )

    submission_payload = {
        'facility_name': new_facility_name,
        'normalized_facility_name': normalized_name,
        'ward_id': submission_ward.id,
        'sub_county_id': submission_ward.sub_county_id,
    }
    return linked_facility, submission_payload, None


def _serialize_chw_facility_link(chw: CHW):
    summary = chw.facility_link_summary()
    status = summary['facility_link_status']
    message = None
    can_escalate = status == 'approved'
    if status == 'awaiting_approval':
        message = 'Awaiting linked facility approval.'
    elif status == 'not_linked':
        message = 'No linked facility on file.'
    elif status == 'rejected':
        message = 'Linked facility submission was rejected. Please select an existing facility or submit a new one.'

    return {
        **summary,
        'facility_link_message': message,
        'can_perform_facility_escalations': can_escalate,
    }

@bp.route('/auth/register', methods=['POST'])
def register():
    """Register a new user and send OTP for verification"""
    data = request.get_json()
    
    # Validate required fields
    required_fields = ['phone_number', 'first_name', 'last_name', 'pin', 'role']
    for field in required_fields:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    
    # Additional validation for mothers
    if data.get('role') == 'mother':
        mother_fields = ['dob', 'due_date', 'ward_id']
        for field in mother_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required for mother registration'}), 400
    
    phone_number = normalize_phone_number(data['phone_number'])
    first_name = data['first_name'].strip()
    last_name  = data['last_name'].strip()
    pin  = data['pin']
    role = data['role']
    email = data.get('email', '').strip() or None   # optional
    license_number = data.get('license_number', '').strip()
    ward_id = data.get('ward_id')
    ward = None

    # CHW and Nurse require license_number and ward_id
    if role in ('chw', 'nurse'):
        if not license_number:
            return jsonify({'error': 'license_number is required for CHW/Nurse registration'}), 400
        if not ward_id:
            return jsonify({'error': 'ward_id is required for CHW/Nurse registration'}), 400

        ward, ward_error = _parse_ward_or_error(ward_id)
        if ward_error:
            return ward_error

    if role == 'chw':
        _linked_facility, _submission_payload, chw_facility_error = _resolve_chw_facility_selection_or_error(data, ward)
        if chw_facility_error:
            return chw_facility_error
    
    # Validate phone number format
    if not validate_phone_number(phone_number):
        return jsonify({'error': 'Please enter phone number in 07xxxxxxxx format (e.g., 0712345678)'}), 400
    
    # Validate PIN length and format
    if len(pin) < 4 or len(pin) > 8:
        return jsonify({'error': 'PIN must be between 4 and 8 characters'}), 400
    
    # Validate name fields
    if len(first_name) < 2:
        return jsonify({'error': 'First name must be at least 2 characters long'}), 400
    if len(last_name) < 1:
        return jsonify({'error': 'Last name is required'}), 400
    
    # Validate role
    if role not in ['mother', 'chw', 'nurse']:
        return jsonify({'error': 'Invalid role. Must be mother, chw, or nurse'}), 400
    
    # Deprecation notice for nurse role
    if role == 'nurse':
        return jsonify({
            'error': 'Nurse registration is deprecated',
            'message': 'The standalone nurse role is no longer supported. Please join a healthcare facility instead.',
            'redirect': '/login/facility'
        }), 410  # 410 Gone status code
    
    # Check if user already exists
    existing_user = User.query.filter_by(phone_number=phone_number).first()
    if existing_user:
        return jsonify({'error': 'User with this phone number already exists'}), 409
    
    try:
        # Create new user (unverified)
        user = User(
            phone_number=phone_number,
            first_name=first_name,
            last_name=last_name,
            email=email,
            pin_hash=hash_pin(pin),
            role=role,
            is_verified=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        db.session.add(user)
        db.session.flush()  # Get user ID without committing
        
        # Generate and store OTP
        otp_code = generate_otp()
        verification = Verification(
            user_id=user.id,
            phone_number=phone_number,
            code=otp_code,
            status='pending',
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
        )
        
        db.session.add(verification)
        db.session.commit()
        
        success, delivery_msg, delivery_method = send_otp(phone_number, otp_code)
        service = get_otp_service()
        service.log_otp_delivery(
            phone_number=phone_number,
            success=success,
            method=delivery_method,
            error=None if success else delivery_msg
        )

        if not success:
            log.warning("[OTP] Failed to deliver OTP to %s: %s", phone_number, delivery_msg)

        return jsonify({
            'message': 'Registration successful. Please verify your phone number.',
            'user_id': user.id,
            'role': role,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'expires_in': '10 minutes',
            'otp_delivery_status': 'sent' if success else 'pending_retry'
        }), 201
        
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'Registration failed. Please try again.'}), 500

@bp.route('/auth/verify-otp', methods=['POST'])
def verify_otp():
    """Verify OTP and activate user account, then create the role-specific profile."""
    data = request.get_json()

    phone_number = normalize_phone_number(data.get('phone_number', ''))
    otp_code = data.get('otp_code')

    if not phone_number or not otp_code:
        return jsonify({'error': 'Phone number and verification code are required'}), 400

    # Find pending verification
    verification = Verification.query.filter_by(
        phone_number=phone_number,
        code=otp_code,
        status='pending'
    ).first()

    if not verification:
        return jsonify({'error': 'Invalid verification code. Please check the code and try again.'}), 400

    # Check if OTP is expired
    expires_at = verification.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        verification.status = 'expired'
        db.session.commit()
        return jsonify({'error': 'Verification code has expired. Please request a new one.'}), 400

    user = User.query.get(verification.user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    now = datetime.now(timezone.utc)
    profile_obj = None  # will hold the role-specific object to add

    # ── Step 1: Validate role-specific fields and build the profile object ──
    # (we do this BEFORE touching the session so early-return leaves DB clean)
    if user.role == 'chw' and not user.chw:
        license_number = data.get('license_number', '').strip()
        ward_id        = data.get('ward_id')
        if not license_number:
            return jsonify({'error': 'license_number is required to complete CHW registration'}), 400
        if not ward_id:
            return jsonify({'error': 'ward_id is required to complete CHW registration'}), 400
        ward, ward_error = _parse_ward_or_error(ward_id)
        if ward_error:
            return ward_error

        linked_facility, submission_payload, chw_facility_error = _resolve_chw_facility_selection_or_error(data, ward)
        if chw_facility_error:
            return chw_facility_error

        profile_obj = CHW(
            user_id=user.id,
            chw_name=user.name,
            license_number=license_number,
            location=f"{ward.sub_county.name} > {ward.name}",
            ward_id=ward.id,
            sub_county_id=ward.sub_county_id,
            linked_facility_id=linked_facility.id if linked_facility else None,
            created_at=now
        )

    elif user.role == 'nurse' and not user.nurse:
        license_number = data.get('license_number', '').strip()
        ward_id        = data.get('ward_id')
        if not license_number:
            return jsonify({'error': 'license_number is required to complete Nurse registration'}), 400
        if not ward_id:
            return jsonify({'error': 'ward_id is required to complete Nurse registration'}), 400
        ward, ward_error = _parse_ward_or_error(ward_id)
        if ward_error:
            return ward_error
        profile_obj = Nurse(
            user_id=user.id,
            nurse_name=user.name,
            license_number=license_number,
            location=f"{ward.sub_county.name} > {ward.name}",
            ward_id=ward.id,
            sub_county_id=ward.sub_county_id,
            created_at=now
        )

    elif user.role == 'mother' and not user.mother:
        dob_str      = data.get('dob', '').strip()
        due_date_str = data.get('due_date', '').strip()
        ward_id      = data.get('ward_id')
        if not dob_str:
            return jsonify({'error': 'Date of birth (dob) is required to complete mother registration'}), 400
        if not due_date_str:
            return jsonify({'error': 'Due date is required to complete mother registration'}), 400
        if not ward_id:
            return jsonify({'error': 'ward_id is required to complete mother registration'}), 400

        ward, ward_error = _parse_ward_or_error(ward_id)
        if ward_error:
            return ward_error

        try:
            dob_date = datetime.strptime(dob_str, '%Y-%m-%d').date()
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format. Please use YYYY-MM-DD (e.g. 1995-06-15).'}), 400
        profile_obj = Mother(
            user_id=user.id,
            mother_name=user.name,
            dob=dob_date,
            due_date=due_date,
            location=f"{ward.sub_county.name} > {ward.name}",
            ward_id=ward.id,
            sub_county_id=ward.sub_county_id,
            created_at=now
        )

    # ── Step 2: Mark user verified and commit everything atomically ──
    user.is_verified = True
    user.updated_at  = now
    verification.status = 'verified'

    if profile_obj is not None:
        db.session.add(profile_obj)

        # Bootstrap default reminders if mother
        if user.role == 'mother':
            from models import Reminder
            default_reminders = [
                Reminder(user_id=user.id, title="Take Prenatal Vitamins", type="medication", time_string="08:00", frequency="daily", icon="MED"),
                Reminder(user_id=user.id, title="Drink 8 glasses of water", type="hydration", time_string="12:00", frequency="daily", icon="H2O"),
                Reminder(user_id=user.id, title="30-minute walk", type="exercise", time_string="17:00", frequency="daily", icon="WALK"),
                Reminder(user_id=user.id, title="Daily check-in", type="health", time_string="21:00", frequency="daily", icon="CHECK"),
                Reminder(user_id=user.id, title="Read pregnancy article", type="education", time_string="10:00", frequency="daily", icon="READ")
            ]
            for r in default_reminders:
                db.session.add(r)

    created_assignments = []
    if profile_obj is not None and user.role in ('mother', 'chw'):
        db.session.flush()
        if user.role == 'mother':
            assignment, changed = assign_mother_if_possible(
                profile_obj.id,
                assignment_method=ASSIGNMENT_METHOD_AUTO_WARD_MATCH,
            )
            if changed and assignment:
                created_assignments.append(assignment)
        elif user.role == 'chw':
            if submission_payload:
                submission = CHWFacilitySubmission(
                    submitted_by_user_id=user.id,
                    chw_id=profile_obj.id,
                    facility_name=submission_payload['facility_name'],
                    normalized_facility_name=submission_payload['normalized_facility_name'],
                    ward_id=submission_payload['ward_id'],
                    sub_county_id=submission_payload['sub_county_id'],
                    status='pending',
                )
                db.session.add(submission)
                db.session.flush()
                profile_obj.pending_facility_submission_id = submission.id

            created_assignments = backfill_chw_from_ward_backlog(
                profile_obj.id,
                assignment_method=ASSIGNMENT_METHOD_AUTO_WARD_MATCH,
            )

    try:
        db.session.commit()
    except Exception as commit_error:
        db.session.rollback()
        print(f"[ERROR] verify_otp commit failed for user {user.id}: {commit_error}")
        return jsonify({'error': 'Failed to complete registration. Please try again.'}), 500

    for assignment in created_assignments:
        emit_assignment_event("assignment:created", assignment)

    # ── Step 3: Return the profile_id so frontend can cache it ──
    profile_id = None
    if user.role == 'chw' and user.chw:
        profile_id = user.chw.id
    elif user.role == 'nurse' and user.nurse:
        profile_id = user.nurse.id
    elif user.role == 'mother' and user.mother:
        profile_id = user.mother.id

    return jsonify({
        'message': 'Phone number verified successfully. You can now login.',
        'user_id': user.id,
        'role': user.role,
        'profile_id': profile_id,
        'chw_facility_link': _serialize_chw_facility_link(user.chw) if user.role == 'chw' and user.chw else None,
    }), 200

@bp.route('/auth/login', methods=['POST'])
def login():
    """Login with hybrid authentication (JWT + Session)"""
    data = request.get_json()

    raw_phone = (data.get('phone_number') or '').strip()
    email = (data.get('email') or '').strip().lower() or None
    role_hint = (data.get('role') or '').strip().lower() or None

    phone_number = normalize_phone_number(raw_phone) if raw_phone else None
    pin = data.get('pin')
    otp_code = (data.get('otp_code') or '').strip()

    if (not phone_number and not email) or not pin:
        return jsonify({'error': 'Please enter PIN and phone number or email'}), 400

    # Validate phone number format when phone is supplied
    if phone_number and not validate_phone_number(phone_number):
        return jsonify({'error': 'Please enter phone number in 07xxxxxxxx format'}), 400

    user = _find_user_by_contact(phone_number=phone_number, email=email)
    facility_account = _find_facility_account_by_contact(phone_number=phone_number, email=email)

    if not user and not facility_account:
        return jsonify({'error': 'No account found with provided phone/email. Please register first.'}), 404

    subject_type, user_pin_ok, facility_pin_ok = _resolve_login_subject(
        user=user,
        facility_account=facility_account,
        pin=pin,
        role_hint=role_hint,
    )

    if not subject_type:
        return jsonify({'error': 'Incorrect PIN. Please try again.'}), 401

    if subject_type == 'facility':
        if not facility_account:
            return jsonify({'error': 'Facility account not found'}), 404

        if not facility_account.is_active:
            return jsonify({'error': 'Facility account is inactive'}), 403

        if not facility_account.pin_hash:
            return jsonify({'error': 'PIN is not set for this facility account'}), 400

        if facility_account.role not in {'admin', 'doctor', 'nurse'}:
            return jsonify({'error': 'Unsupported facility account role'}), 403

        active_membership = FacilityStaff.query.filter_by(account_id=facility_account.id, status='active').first()
        if facility_account.role != 'admin' and not active_membership:
            return jsonify({'error': 'Active facility membership not found'}), 403

        now = datetime.now(timezone.utc)
        otp_phone = facility_account.phone_number

        # Enforce OTP verification for facility login as well.
        if not otp_code:
            if not otp_phone or not validate_phone_number(otp_phone):
                return jsonify({'error': 'A valid support line is required for OTP login verification'}), 400

            stale_tokens = OTPToken.query.filter_by(
                phone_number=otp_phone,
                purpose='facility_pin_login',
                is_used=False,
            ).all()
            for token in stale_tokens:
                token.is_used = True
                token.used_at = now

            login_otp_code = generate_otp()
            login_otp = OTPToken(
                phone_number=otp_phone,
                email=facility_account.email,
                otp_code=login_otp_code,
                purpose='facility_pin_login',
                facility_id=facility_account.facility_id,
                attempts=0,
                max_attempts=5,
                is_used=False,
                created_at=now,
                expires_at=now + timedelta(minutes=10),
            )
            db.session.add(login_otp)
            db.session.commit()

            success, delivery_msg, delivery_method = send_otp(otp_phone, login_otp_code)
            service = get_otp_service()
            service.log_otp_delivery(
                phone_number=otp_phone,
                success=success,
                method=delivery_method,
                error=None if success else delivery_msg,
            )

            if not success:
                log.warning("[OTP] Failed to deliver facility login OTP to %s: %s", otp_phone, delivery_msg)

            return jsonify({
                'message': 'OTP sent. Enter the code to complete login.',
                'requires_otp': True,
                'expires_in': '10 minutes',
                'otp_delivery_status': 'sent' if success else 'pending_retry'
            }), 200

        login_otp = OTPToken.query.filter_by(
            phone_number=otp_phone,
            purpose='facility_pin_login',
            is_used=False,
        ).order_by(OTPToken.created_at.desc()).first()

        if not login_otp:
            return jsonify({'error': 'No active login OTP found. Please request a new code.'}), 400

        if not login_otp.is_valid():
            login_otp.attempts += 1
            db.session.commit()
            return jsonify({'error': 'Login OTP expired or max attempts reached. Request a new code.'}), 400

        if login_otp.otp_code != otp_code:
            login_otp.attempts += 1
            db.session.commit()
            return jsonify({'error': 'Invalid OTP. Please try again.'}), 401

        login_otp.is_used = True
        login_otp.used_at = now

        facility_identity = f'facility:{facility_account.id}'
        access_token = create_access_token(identity=facility_identity)
        refresh_token = create_refresh_token(identity=facility_identity)

        facility_account.updated_at = now
        db.session.commit()

        return jsonify({
            'message': 'Login successful',
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': {
                'id': facility_account.id,
                'phone_number': facility_account.phone_number,
                'first_name': facility_account.first_name,
                'last_name': facility_account.last_name,
                'name': facility_account.name,
                'role': 'facility_staff',
                'profile_completed': bool(facility_account.profile_completed),
                'facility_id': facility_account.facility_id,
                'account_role': facility_account.role,
            }
        }), 200

    if not user:
        return jsonify({'error': 'User account not found'}), 404

    if not user_pin_ok:
        return jsonify({'error': 'Incorrect PIN. Please try again.'}), 401

    if not user.is_verified:
        return jsonify({'error': 'Please verify your phone number first. Check for SMS with verification code.'}), 401

    now = datetime.now(timezone.utc)

    # Enforce OTP verification for login after PIN check.
    if not otp_code:
        stale_login_otps = OTPToken.query.filter_by(
            phone_number=user.phone_number,
            purpose='user_login',
            is_used=False,
        ).all()

        for token in stale_login_otps:
            token.is_used = True
            token.used_at = now

        login_otp_code = generate_otp()
        login_otp = OTPToken(
            phone_number=user.phone_number,
            email=user.email,
            otp_code=login_otp_code,
            purpose='user_login',
            facility_id=None,
            attempts=0,
            max_attempts=5,
            is_used=False,
            created_at=now,
            expires_at=now + timedelta(minutes=10),
        )

        db.session.add(login_otp)
        db.session.commit()

        success, delivery_msg, delivery_method = send_otp(user.phone_number, login_otp_code)
        service = get_otp_service()
        service.log_otp_delivery(
            phone_number=user.phone_number,
            success=success,
            method=delivery_method,
            error=None if success else delivery_msg,
        )

        if not success:
            log.warning("[OTP] Failed to deliver login OTP to %s: %s", user.phone_number, delivery_msg)

        return jsonify({
            'message': 'OTP sent. Enter the code to complete login.',
            'requires_otp': True,
            'expires_in': '10 minutes',
            'otp_delivery_status': 'sent' if success else 'pending_retry'
        }), 200

    login_otp = OTPToken.query.filter_by(
        phone_number=user.phone_number,
        purpose='user_login',
        is_used=False,
    ).order_by(OTPToken.created_at.desc()).first()

    if not login_otp:
        return jsonify({'error': 'No active login OTP found. Please request a new code.'}), 400

    if not login_otp.is_valid():
        login_otp.attempts += 1
        db.session.commit()
        return jsonify({'error': 'Login OTP expired or max attempts reached. Request a new code.'}), 400

    if login_otp.otp_code != otp_code:
        login_otp.attempts += 1
        db.session.commit()
        return jsonify({'error': 'Invalid OTP. Please try again.'}), 401

    login_otp.is_used = True
    login_otp.used_at = now
    
    
    # Get device info from request headers
    device_info = request.headers.get('User-Agent', 'Unknown Device')
    ip_address = request.remote_addr
    
    # Create JWT tokens (identity must be string)
    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))
    
    # Create session token for database tracking (not Flask session)
    session_token = create_user_session(user.id, device_info, ip_address)
    
    # Get profile_id based on role
    profile_id = None
    if user.role == 'mother' and user.mother:
        profile_id = user.mother.id
    elif user.role == 'chw' and user.chw:
        profile_id = user.chw.id
    elif user.role == 'nurse' and user.nurse:
        profile_id = user.nurse.id
    
    # Update last login
    user.updated_at = now
    db.session.commit()
    
    return jsonify({
        'message': 'Login successful',
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': {
            'id': user.id,
            'phone_number': user.phone_number,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'name': user.name,
            'role': user.role,
            'profile_id': profile_id,
            'chw_facility_link': _serialize_chw_facility_link(user.chw) if user.role == 'chw' and user.chw else None,
        }
    }), 200

@bp.route('/auth/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """Refresh access token"""
    identity = str(get_jwt_identity() or '')

    if identity.startswith('facility:'):
        try:
            account_id = int(identity.split(':', 1)[1])
        except ValueError:
            return jsonify({'error': 'Invalid user'}), 401

        account = FacilityAccount.query.get(account_id)
        if not account or not account.is_active:
            return jsonify({'error': 'Invalid user'}), 401

        new_access_token = create_access_token(identity=identity)
        return jsonify({'access_token': new_access_token}), 200

    current_user_id = identity
    user = User.query.get(current_user_id)

    if not user or not user.is_verified:
        return jsonify({'error': 'Invalid user'}), 401

    new_access_token = create_access_token(identity=str(current_user_id))
    
    return jsonify({
        'access_token': new_access_token
    }), 200

@bp.route('/auth/logout', methods=['POST'])
@require_auth
def logout():
    """Logout from current session"""
    user = get_current_user()
    current_session_token = session.get('session_token')
    
    # Invalidate current session
    if current_session_token:
        from models import UserSession
        user_session = UserSession.query.filter_by(session_token=current_session_token).first()
        if user_session:
            user_session.is_active = False
            db.session.commit()
    
    # Clear Flask session
    session.clear()
    
    return jsonify({'message': 'Logout successful'}), 200

@bp.route('/auth/logout-all', methods=['POST'])
@require_auth
def logout_all():
    """Logout from all sessions"""
    user = get_current_user()
    current_session_token = session.get('session_token')
    
    # Logout all sessions except current
    sessions_logged_out = logout_user_sessions(user.id, current_session_token)
    
    return jsonify({
        'message': f'Logged out from {sessions_logged_out} other sessions'
    }), 200

@bp.route('/auth/profile', methods=['GET'])
@require_auth
def get_profile():
    """Get current user profile"""
    user = get_current_user()
    
    # Get profile_id based on role
    profile_id = None
    if user.role == 'mother' and user.mother:
        profile_id = user.mother.id
    elif user.role == 'chw' and user.chw:
        profile_id = user.chw.id
    elif user.role == 'nurse' and user.nurse:
        profile_id = user.nurse.id
    
    profile_data = {
        'id': user.id,
        'phone_number': user.phone_number,
        'name': user.name,
        'role': user.role,
        'profile_id': profile_id,
        'is_verified': user.is_verified,
        'created_at': user.created_at.isoformat(),
        'auth_method': getattr(request, 'auth_method', 'jwt'),
        'chw_facility_link': _serialize_chw_facility_link(user.chw) if user.role == 'chw' and user.chw else None,
    }
    
    # Add role-specific data
    if user.role == 'mother' and user.mother:
        profile_data['mother_profile'] = {
            'mother_name': user.mother.mother_name,
            'dob': user.mother.dob.isoformat(),
            'due_date': user.mother.due_date.isoformat(),
            'location': user.mother.location
        }
    elif user.role == 'chw' and user.chw:
        profile_data['chw_profile'] = {
            'chw_name': user.chw.chw_name,
            'license_number': user.chw.license_number,
            'location': user.chw.location,
            **_serialize_chw_facility_link(user.chw),
        }
    elif user.role == 'nurse' and user.nurse:
        profile_data['nurse_profile'] = {
            'nurse_name': user.nurse.nurse_name,
            'license_number': user.nurse.license_number,
            'location': user.nurse.location
        }
    
    return jsonify(profile_data), 200

@bp.route('/auth/resend-otp', methods=['POST'])
def resend_otp():
    """Resend OTP for phone verification"""
    data = request.get_json()
    phone_number = normalize_phone_number(data.get('phone_number', ''))
    
    if not phone_number:
        return jsonify({'error': 'Phone number is required'}), 400

    if not validate_phone_number(phone_number):
        return jsonify({'error': 'Please enter phone number in 07xxxxxxxx format'}), 400
    
    # Find unverified user
    user = User.query.filter_by(phone_number=phone_number, is_verified=False).first()
    if not user:
        return jsonify({'error': 'No unverified user found with this phone number'}), 404
    
    # Invalidate old OTPs
    old_verifications = Verification.query.filter_by(
        phone_number=phone_number,
        status='pending'
    ).all()
    
    for verification in old_verifications:
        verification.status = 'expired'
    
    # Generate new OTP
    otp_code = generate_otp()
    verification = Verification(
        user_id=user.id,
        phone_number=phone_number,
        code=otp_code,
        status='pending',
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
    )
    
    db.session.add(verification)
    db.session.commit()

    success, delivery_msg, delivery_method = send_otp(phone_number, otp_code)
    service = get_otp_service()
    service.log_otp_delivery(
        phone_number=phone_number,
        success=success,
        method=delivery_method,
        error=None if success else delivery_msg
    )

    if not success:
        log.warning("[OTP] Failed to resend OTP to %s: %s", phone_number, delivery_msg)

    return jsonify({
        'message': 'New OTP sent successfully',
        'expires_in': '10 minutes',
        'otp_delivery_status': 'sent' if success else 'failed'
    }), 200


@bp.route('/auth/request-pin-reset-otp', methods=['POST'])
def request_pin_reset_otp():
    """Issue an OTP for phone-based PIN recovery."""
    data = request.get_json() or {}
    phone_number = normalize_phone_number(data.get('phone_number', ''))
    role_hint = data.get('role')

    if not phone_number:
        return jsonify({'error': 'Phone number is required'}), 400

    if not validate_phone_number(phone_number):
        return jsonify({'error': 'Please enter phone number in 07xxxxxxxx format'}), 400

    subject_type, subject = _resolve_pin_reset_subject(phone_number, role_hint)
    if not subject_type or not subject:
        return jsonify({'error': 'No account found with that phone number'}), 404

    if subject_type == 'user' and not subject.is_verified:
        return jsonify({'error': 'Please verify this account before resetting the PIN'}), 403

    if subject_type == 'facility' and not subject.is_active:
        return jsonify({'error': 'This facility account is inactive'}), 403

    now = datetime.now(timezone.utc)
    purpose = 'pin_reset_facility' if subject_type == 'facility' else 'pin_reset_user'

    stale_tokens = OTPToken.query.filter_by(
        phone_number=phone_number,
        purpose=purpose,
        is_used=False,
    ).all()

    for token in stale_tokens:
        token.is_used = True
        token.used_at = now

    otp_code = generate_otp()
    reset_token = OTPToken(
        phone_number=phone_number,
        email=getattr(subject, 'email', None),
        otp_code=otp_code,
        purpose=purpose,
        facility_id=subject.facility_id if subject_type == 'facility' else None,
        attempts=0,
        max_attempts=5,
        is_used=False,
        created_at=now,
        expires_at=now + timedelta(minutes=10),
    )
    db.session.add(reset_token)
    db.session.commit()

    success, delivery_msg, delivery_method = send_otp(phone_number, otp_code)
    service = get_otp_service()
    service.log_otp_delivery(
        phone_number=phone_number,
        success=success,
        method=delivery_method,
        error=None if success else delivery_msg,
    )

    if not success:
        log.warning("[OTP] Failed to deliver PIN reset OTP to %s: %s", phone_number, delivery_msg)

    return jsonify({
        'message': 'PIN reset OTP sent successfully.',
        'expires_in': '10 minutes',
        'otp_delivery_status': 'sent' if success else 'pending_retry',
    }), 200


@bp.route('/auth/reset-pin', methods=['POST'])
def reset_pin():
    """Verify PIN reset OTP and save a new PIN."""
    data = request.get_json() or {}
    phone_number = normalize_phone_number(data.get('phone_number', ''))
    otp_code = (data.get('otp_code') or '').strip()
    new_pin = (data.get('new_pin') or '').strip()
    role_hint = data.get('role')

    if not phone_number or not otp_code or not new_pin:
        return jsonify({'error': 'Phone number, OTP code, and new PIN are required'}), 400

    if not validate_phone_number(phone_number):
        return jsonify({'error': 'Please enter phone number in 07xxxxxxxx format'}), 400

    if len(new_pin) < 4 or len(new_pin) > 8 or not new_pin.isdigit():
        return jsonify({'error': 'PIN must contain 4 to 8 digits'}), 400

    subject_type, subject = _resolve_pin_reset_subject(phone_number, role_hint)
    if not subject_type or not subject:
        return jsonify({'error': 'No account found with that phone number'}), 404

    purpose = 'pin_reset_facility' if subject_type == 'facility' else 'pin_reset_user'
    reset_token = OTPToken.query.filter_by(
        phone_number=phone_number,
        purpose=purpose,
        is_used=False,
    ).order_by(OTPToken.created_at.desc()).first()

    if not reset_token:
        return jsonify({'error': 'No active PIN reset request found. Please request a new code.'}), 400

    if not reset_token.is_valid():
        reset_token.attempts += 1
        db.session.commit()
        return jsonify({'error': 'PIN reset code expired or max attempts reached. Request a new code.'}), 400

    if reset_token.otp_code != otp_code:
        reset_token.attempts += 1
        db.session.commit()
        return jsonify({'error': 'Invalid OTP. Please try again.'}), 401

    now = datetime.now(timezone.utc)
    reset_token.is_used = True
    reset_token.used_at = now
    subject.pin_hash = hash_pin(new_pin)
    subject.updated_at = now
    db.session.commit()

    return jsonify({
        'message': 'PIN reset successful. You can now sign in with your new PIN.',
    }), 200


@bp.route('/auth/verify-pin-reset-otp', methods=['POST'])
def verify_pin_reset_otp():
    """Validate the OTP for a pending PIN reset without consuming it."""
    data = request.get_json() or {}
    phone_number = normalize_phone_number(data.get('phone_number', ''))
    otp_code = (data.get('otp_code') or '').strip()
    role_hint = data.get('role')

    if not phone_number or not otp_code:
        return jsonify({'error': 'Phone number and OTP code are required'}), 400

    if not validate_phone_number(phone_number):
        return jsonify({'error': 'Please enter phone number in 07xxxxxxxx format'}), 400

    subject_type, subject = _resolve_pin_reset_subject(phone_number, role_hint)
    if not subject_type or not subject:
        return jsonify({'error': 'No account found with that phone number'}), 404

    purpose = 'pin_reset_facility' if subject_type == 'facility' else 'pin_reset_user'
    reset_token = OTPToken.query.filter_by(
        phone_number=phone_number,
        purpose=purpose,
        is_used=False,
    ).order_by(OTPToken.created_at.desc()).first()

    if not reset_token:
        return jsonify({'error': 'No active PIN reset request found. Please request a new code.'}), 400

    if not reset_token.is_valid():
        reset_token.attempts += 1
        db.session.commit()
        return jsonify({'error': 'PIN reset code expired or max attempts reached. Request a new code.'}), 400

    if reset_token.otp_code != otp_code:
        reset_token.attempts += 1
        db.session.commit()
        return jsonify({'error': 'Invalid OTP. Please try again.'}), 401

    return jsonify({
        'message': 'PIN reset OTP verified successfully.',
    }), 200
