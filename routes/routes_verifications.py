from flask import Blueprint, request, jsonify
from models import db, User, Verification
from auth_utils import require_auth, require_role, get_current_user
from auth_utils import generate_otp
from datetime import datetime, timedelta, timezone
import re
from africas_talking_service import send_otp as send_otp_via_provider, get_otp_service

bp = Blueprint('verifications', __name__)

def normalize_phone_number(phone):
    phone = (phone or '').strip()
    cleaned = re.sub(r'[^0-9]', '', phone)
    if cleaned.startswith('07') and len(cleaned) == 10:
        return '+254' + cleaned[1:]
    if cleaned.startswith('254') and len(cleaned) == 12:
        return '+' + cleaned
    if phone.startswith('+254') and len(re.sub(r'[^0-9]', '', phone)) == 12:
        return '+254' + re.sub(r'[^0-9]', '', phone)[3:]
    return phone


def validate_phone_number(phone):
    cleaned = re.sub(r'[^0-9+]', '', phone)
    return bool(re.match(r'^07[0-9]{8}$', cleaned) or re.match(r'^\+254[0-9]{9}$', cleaned))


@bp.route('/verifications/send', methods=['POST'])
def send_otp():
    data = request.get_json()
    phone = normalize_phone_number(data.get('phone', ''))
    if not phone:
        return jsonify({"error": "Phone is required."}), 400
    if not validate_phone_number(phone):
        return jsonify({'error': 'Please enter phone number in 07xxxxxxxx format'}), 400

    now = datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)
    count = Verification.query.filter(
        Verification.phone_number == phone,
        Verification.created_at >= one_hour_ago
    ).count()
    if count >= 5:
        return jsonify({"error": "OTP request limit reached. Try again later."}), 429

    # Expire any previous pending OTPs for this phone
    Verification.query.filter_by(phone_number=phone, status='pending').update({"status": "expired"})
    code = generate_otp()
    expires_at = now + timedelta(minutes=10)
    user = User.query.filter_by(phone_number=phone).first()
    verification = Verification(
        user_id=user.id if user else None,
        phone_number=phone,
        code=code,
        status='pending',
        created_at=now,
        expires_at=expires_at
    )
    db.session.add(verification)
    db.session.commit()

    success, delivery_msg, delivery_method = send_otp_via_provider(phone, code)
    service = get_otp_service()
    service.log_otp_delivery(
        phone_number=phone,
        success=success,
        method=delivery_method,
        error=None if success else delivery_msg
    )

    return jsonify({
        "message": "OTP sent successfully.",
        "expires_in": "10 minutes",
        "otp_delivery_status": "sent" if success else "failed"
    }), 200

@bp.route('/verifications/verify', methods=['POST'])
def verify_otp():
    data = request.get_json()
    phone = normalize_phone_number(data.get('phone', ''))
    code = str(data.get('code', '')).strip()
    if not phone or not code:
        return jsonify({"error": "Phone and code are required."}), 400
    if not validate_phone_number(phone):
        return jsonify({'error': 'Please enter phone number in 07xxxxxxxx format'}), 400
    if not re.fullmatch(r"\d{5}", code):
        return jsonify({"error": "OTP code must be a 5-digit number."}), 400

    now = datetime.now(timezone.utc)
    verification = Verification.query.filter_by(phone_number=phone, code=code, status='pending').order_by(Verification.created_at.desc()).first()
    if not verification:
        return jsonify({"error": "Invalid or expired OTP."}), 400
    if verification.expires_at < now:
        verification.status = 'expired'
        db.session.commit()
        return jsonify({"error": "OTP has expired."}), 400
    verification.status = 'verified'
    db.session.commit()
    return jsonify({"message": "OTP verified successfully."}), 200
