from flask import Blueprint, request, jsonify, session
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity
from models import db, User, Verification, Mother, CHW, Nurse
from auth_utils import (
    generate_otp, hash_pin, verify_pin, create_user_session, 
    validate_session_token, require_auth, get_current_user, logout_user_sessions
)
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError
import random
import re
import json

bp = Blueprint('auth', __name__)

def normalize_phone_number(phone):
    """Normalize phone number from 07xxxxxxxx to +254xxxxxxxx format"""
    # Remove all spaces and special characters
    cleaned = re.sub(r'[^0-9]', '', phone)
    
    # Only handle 07xxxxxxxx format
    if cleaned.startswith('07') and len(cleaned) == 10:
        # Convert 07xxxxxxxx to +254xxxxxxxx
        return '+254' + cleaned[1:]
    
    # Return as-is if not in expected format (will fail validation)
    return phone

def validate_phone_number(phone):
    """Validate Kenyan phone number - temporarily allow both formats"""
    # Remove all spaces and special characters
    cleaned = re.sub(r'[^0-9+]', '', phone)
    
    # Check if it's 07xxxxxxxx format
    if re.match(r'^07[0-9]{8}$', cleaned):
        return True
    
    # Also temporarily accept +254xxxxxxx format for existing users
    if re.match(r'^\+254[0-9]{9}$', cleaned):
        return True
    
    return False

@bp.route('/auth/register', methods=['POST'])
def register():
    """Register a new user and send OTP for verification"""
    data = request.get_json()
    
    # Validate required fields
    required_fields = ['phone_number', 'first_name', 'last_name', 'pin', 'role']
    for field in required_fields:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    
    phone_number = normalize_phone_number(data['phone_number'])
    first_name = data['first_name'].strip()
    last_name  = data['last_name'].strip()
    pin  = data['pin']
    role = data['role']
    email = data.get('email', '').strip() or None   # optional
    license_number = data.get('license_number', '').strip()
    location = data.get('location', '').strip()

    # CHW and Nurse require license_number and location
    if role in ('chw', 'nurse'):
        if not license_number:
            return jsonify({'error': 'license_number is required for CHW/Nurse registration'}), 400
        if not location:
            return jsonify({'error': 'location is required for CHW/Nurse registration'}), 400
    
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
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
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
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(minutes=10)
        )
        
        db.session.add(verification)
        db.session.commit()
        
        # In production, send OTP via SMS/WhatsApp
        # For now, return it in response for testing
        return jsonify({
            'message': 'Registration successful. Please verify your phone number.',
            'user_id': user.id,
            'role': role,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'otp_code': otp_code,  # Remove this in production
            'expires_in': '10 minutes'
        }), 201
        
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'Registration failed. Please try again.'}), 500

@bp.route('/auth/verify-otp', methods=['POST'])
def verify_otp():
    """Verify OTP and activate user account"""
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
        return jsonify({'error': 'Invalid OTP code'}), 400
    
    # Check if OTP is expired
    if verification.expires_at < datetime.utcnow():
        verification.status = 'expired'
        db.session.commit()
        return jsonify({'error': 'OTP code has expired'}), 400
    
    # Verify and activate user
    user = User.query.get(verification.user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    user.is_verified = True
    user.updated_at = datetime.utcnow()
    verification.status = 'verified'

    # --- Auto-create the role-specific profile if it doesn't exist yet ---
    now = datetime.utcnow()
    try:
        if user.role == 'chw' and not user.chw:
            license_number = data.get('license_number', '').strip()
            location = data.get('location', '').strip()
            chw = CHW(
                user_id=user.id,
                chw_name=user.name,
                license_number=license_number or 'PENDING',
                location=location or 'PENDING',
                created_at=now
            )
            db.session.add(chw)

        elif user.role == 'nurse' and not user.nurse:
            license_number = data.get('license_number', '').strip()
            location = data.get('location', '').strip()
            nurse = Nurse(
                user_id=user.id,
                nurse_name=user.name,
                license_number=license_number or 'PENDING',
                location=location or 'PENDING',
                created_at=now
            )
            db.session.add(nurse)

        elif user.role == 'mother' and not user.mother:
            # dob / due_date are nullable — mother completes profile from dashboard
            mother = Mother(
                user_id=user.id,
                mother_name=user.name,
                created_at=now
            )
            db.session.add(mother)

    except Exception as profile_error:
        # Don't block verification if profile creation fails — log and continue
        print(f"[WARN] Could not auto-create role profile for user {user.id}: {profile_error}")

    db.session.commit()

    # Determine the created profile id for the response
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
        'profile_id': profile_id
    }), 200

@bp.route('/auth/login', methods=['POST'])
def login():
    """Login with hybrid authentication (JWT + Session)"""
    data = request.get_json()
    
    phone_number = data.get('phone_number')
    pin = data.get('pin')
    
    if not phone_number or not pin:
        return jsonify({'error': 'Please enter both phone number and PIN'}), 400
    
    # Normalize phone number
    normalized_phone = normalize_phone_number(phone_number)
    
    # Validate phone number format
    if not validate_phone_number(phone_number):
        return jsonify({'error': 'Please enter phone number in 07xxxxxxxx format'}), 400
    
    # Find user - try both the normalized format and original format
    user = User.query.filter_by(phone_number=normalized_phone).first()
    
    # If not found with normalized phone, try to find with +254 format (for existing users)
    if not user and phone_number.startswith('07'):
        legacy_phone = '+254' + phone_number[1:]  # Convert 07xxx to +254xxx
        user = User.query.filter_by(phone_number=legacy_phone).first()
        print(f"Trying legacy format: {legacy_phone}")
    
    if not user:
        print(f"No user found for: {phone_number} or {normalized_phone}")
        return jsonify({'error': 'No account found with this phone number. Please register first.'}), 404
    
    if not verify_pin(pin, user.pin_hash):
        return jsonify({'error': 'Incorrect PIN. Please try again.'}), 401
    
    if not user.is_verified:
        return jsonify({'error': 'Please verify your phone number first. Check for SMS with verification code.'}), 401
    
    
    # Get device info from request headers
    device_info = request.headers.get('User-Agent', 'Unknown Device')
    ip_address = request.remote_addr
    
    # Create JWT tokens (identity must be string)
    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))
    
    # Create session token for database tracking (not Flask session)
    session_token = create_user_session(user.id, device_info, ip_address)
    
    # Update last login
    user.updated_at = datetime.utcnow()
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
            'role': user.role
        }
    }), 200

@bp.route('/auth/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """Refresh access token"""
    current_user_id = get_jwt_identity()
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
    
    profile_data = {
        'id': user.id,
        'phone_number': user.phone_number,
        'name': user.name,
        'role': user.role,
        'is_verified': user.is_verified,
        'created_at': user.created_at.isoformat(),
        'auth_method': request.auth_method
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
            'location': user.chw.location
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
    phone_number = data.get('phone_number')
    
    if not phone_number:
        return jsonify({'error': 'Phone number is required'}), 400
    
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
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=10)
    )
    
    db.session.add(verification)
    db.session.commit()
    
    return jsonify({
        'message': 'New OTP sent successfully',
        'otp_code': otp_code,  # Remove this in production
        'expires_in': '10 minutes'
    }), 200
