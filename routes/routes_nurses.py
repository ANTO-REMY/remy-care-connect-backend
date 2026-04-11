from flask import Blueprint, request, jsonify
from models import db, User, Nurse, Ward
from auth_utils import require_auth, require_role, get_current_user, hash_pin
from datetime import datetime, timezone
from socket_manager import socketio
import logging

bp = Blueprint('nurses', __name__)

def _split_full_name(full_name: str):
    parts = full_name.strip().split(' ', 1)
    return parts[0], parts[1] if len(parts) > 1 else ''

@bp.route('/nurses/register', methods=['POST'])
def register_nurse():
    data = request.get_json()
    logging.error(f"[NURSE REGISTER] {request.method} {request.path} - DATA: {data}")
    required_fields = ['full_name', 'phone', 'license_number', 'ward_id', 'pin', 'confirm_pin']
    for field in required_fields:
        if not data.get(field):
            logging.error(f"[NURSE REGISTER] Missing field: {field}")
            return jsonify({"error": f"{field} is required."}), 400

    ward = Ward.query.get(data['ward_id'])
    if not ward:
        return jsonify({"error": f"Ward with id {data['ward_id']} not found"}), 400

    if User.query.filter_by(phone_number=data['phone']).first():
        logging.error(f"[NURSE REGISTER] Phone number already registered: {data['phone']}")
        return jsonify({"error": "Phone number already registered."}), 409
    if data['pin'] != data['confirm_pin']:
        logging.error("[NURSE REGISTER] PIN and Confirm PIN do not match.")
        return jsonify({"error": "PIN and Confirm PIN do not match."}), 400
    try:
        now = datetime.now(timezone.utc)
        first_name, last_name = _split_full_name(data['full_name'])
        user = User(
            phone_number=data['phone'],
            first_name=first_name,
            last_name=last_name,
            pin_hash=hash_pin(data['pin']),
            role='nurse',
            is_verified=True,
            created_at=now,
            updated_at=now
        )
        db.session.add(user)
        db.session.flush()
        location_str = f"{ward.sub_county.name} > {ward.name}"
        nurse = Nurse(
            user_id=user.id,
            nurse_name=data['full_name'],
            license_number=data['license_number'],
            location=location_str,
            ward_id=ward.id,
            sub_county_id=ward.sub_county_id,
            created_at=now
        )
        db.session.add(nurse)
        db.session.commit()
        logging.info(f"[NURSE REGISTER] Success for phone: {data['phone']}")
        return jsonify({"message": "Nurse registered successfully", "nurse_id": nurse.id}), 201
    except Exception as e:
        db.session.rollback()
        logging.error(f"[NURSE REGISTER] Exception: {str(e)}")
        return jsonify({"error": str(e)}), 500

@bp.route('/nurses/complete-profile', methods=['POST'])
@require_auth
@require_role('nurse')
def complete_nurse_profile():
    """Complete nurse profile after registration and verification"""
    user = get_current_user()
    
    # Check if profile already exists
    if user.nurse:
        return jsonify({"error": "Nurse profile already exists"}), 409
    
    data = request.get_json()
    required_fields = ['license_number', 'location']
    for field in required_fields:
        if not data.get(field):
            return jsonify({"error": f"{field} is required."}), 400
    
    try:
        nurse = Nurse(
            user_id=user.id,
            nurse_name=user.name,
            license_number=data['license_number'],
            location=data['location'],
            created_at=datetime.now(timezone.utc)
        )
        db.session.add(nurse)
        db.session.commit()
        return jsonify({"message": "Nurse profile completed successfully", "nurse_id": nurse.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@bp.route('/nurses/profile', methods=['GET'])
@require_auth
@require_role('nurse')
def get_current_nurse_profile():
    """Get current nurse's profile based on JWT token"""
    user = get_current_user()
    nurse = Nurse.query.filter_by(user_id=user.id).first()
    if not nurse:
        return jsonify({"error": "Nurse profile not found."}), 404
    return jsonify({
        "id": nurse.id,
        "user_id": user.id,
        "name": nurse.nurse_name,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone_number": user.phone_number,
        "license_number": nurse.license_number,
        "location": nurse.location,
        "created_at": nurse.created_at.isoformat()
    }), 200

@bp.route('/nurses/<int:nurse_id>', methods=['GET'])
def get_nurse(nurse_id):
    nurse = Nurse.query.get(nurse_id)
    if not nurse:
        return jsonify({"error": "Nurse not found."}), 404
    user = User.query.get(nurse.user_id)
    return jsonify({
        "nurse_id": nurse.id,
        "user_id": user.id,
        "name": nurse.nurse_name,
        "phone_number": user.phone_number,
        "license_number": nurse.license_number,
        "location": nurse.location,
        "created_at": nurse.created_at.isoformat()
    }), 200

@bp.route('/nurses/<int:nurse_id>', methods=['PUT'])
@require_auth
def update_nurse(nurse_id):
    nurse = Nurse.query.get(nurse_id)
    if not nurse:
        return jsonify({"error": "Nurse not found."}), 404
    data = request.get_json()
    user = User.query.get(nurse.user_id)
    if 'full_name' in data:
        user.first_name, user.last_name = _split_full_name(data['full_name'])
        nurse.nurse_name = data['full_name'].strip()
    elif 'first_name' in data or 'last_name' in data:
        if 'first_name' in data:
            user.first_name = data['first_name'].strip()
        if 'last_name' in data:
            user.last_name = data['last_name'].strip()
        nurse.nurse_name = user.name
    if 'license_number' in data:
        nurse.license_number = data['license_number']
    if 'location' in data:
        nurse.location = data['location']
    db.session.commit()
    # ── WebSocket push ────────────────────────────────────────────────────
    socketio.emit("nurse:profile_updated", {
        "nurse_id": nurse.id,
        "user_id": nurse.user_id,
        "name": nurse.nurse_name,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "license_number": nurse.license_number,
        "location": nurse.location,
    }, to=f"nurse:{nurse.id}")
    socketio.emit("nurse:profile_updated", {
        "nurse_id": nurse.id,
        "user_id": nurse.user_id,
        "name": nurse.nurse_name,
    }, to=f"user:{nurse.user_id}")
    # ─────────────────────────────────────────────────────────────────────
    return jsonify({"message": "Nurse profile updated successfully."}), 200

@bp.route('/nurses/<int:nurse_id>', methods=['DELETE'])
@require_auth
def delete_nurse(nurse_id):
    nurse = Nurse.query.get(nurse_id)
    if not nurse:
        return jsonify({"error": "Nurse not found."}), 404
    user = User.query.get(nurse.user_id)
    db.session.delete(nurse)
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "Nurse profile deleted successfully."}), 200

@bp.route('/nurses', methods=['GET'])
def list_nurses():
    nurses = Nurse.query.all()
    result = []
    for nurse in nurses:
        user = User.query.get(nurse.user_id)
        result.append({
            "nurse_id": nurse.id,
            "user_id": user.id,
            "name": nurse.nurse_name,
            "phone_number": user.phone_number,
            "license_number": nurse.license_number,
            "location": nurse.location,
            "created_at": nurse.created_at.isoformat()
        })
    return jsonify({"nurses": result}), 200
