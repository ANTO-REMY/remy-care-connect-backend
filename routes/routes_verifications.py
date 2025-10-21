from flask import Blueprint, request, jsonify
from models import db, User, Verification
from auth_utils import require_auth, require_role, get_current_user
from datetime import datetime, timedelta
import random

bp = Blueprint('verifications', __name__)

@bp.route('/api/v1/verifications/send', methods=['POST'])
def send_otp():
    data = request.get_json()
    phone = data.get('phone')
    if not phone:
        return jsonify({"error": "Phone is required."}), 400
    now = datetime.utcnow()
    one_hour_ago = now - timedelta(hours=1)
    count = Verification.query.filter(
        Verification.phone_number == phone,
        Verification.created_at >= one_hour_ago
    ).count()
    if count >= 5:
        return jsonify({"error": "OTP request limit reached. Try again later."}), 429
    # Expire any previous pending OTPs for this phone
    Verification.query.filter_by(phone_number=phone, status='pending').update({"status": "expired"})
    code = str(random.randint(10000, 99999))
    expires_at = now + timedelta(minutes=5)
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
    # Here you would send the OTP via SMS
    return jsonify({"message": "OTP sent successfully.", "otp": code}), 200

@bp.route('/api/v1/verifications/verify', methods=['POST'])
def verify_otp():
    data = request.get_json()
    phone = data.get('phone')
    code = data.get('code')
    if not phone or not code:
        return jsonify({"error": "Phone and code are required."}), 400
    now = datetime.utcnow()
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
