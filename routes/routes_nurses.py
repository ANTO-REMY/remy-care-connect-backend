from flask import Blueprint, request, jsonify
from models import db, User, Nurse
from auth_utils import require_auth, require_role, get_current_user
from datetime import datetime

bp = Blueprint('nurses', __name__)

import logging

@bp.route('/nurses/register', methods=['POST'])
def register_nurse():
    data = request.get_json()
    logging.error(f"[NURSE REGISTER] {request.method} {request.path} - DATA: {data}")
    required_fields = ['full_name', 'phone', 'license_number', 'location', 'pin', 'confirm_pin']
    for field in required_fields:
        if not data.get(field):
            logging.error(f"[NURSE REGISTER] Missing field: {field}")
            return jsonify({"error": f"{field} is required."}), 400
    if User.query.filter_by(phone_number=data['phone']).first():
        logging.error(f"[NURSE REGISTER] Phone number already registered: {data['phone']}")
        return jsonify({"error": "Phone number already registered."}), 409
    if data['pin'] != data['confirm_pin']:
        logging.error("[NURSE REGISTER] PIN and Confirm PIN do not match.")
        return jsonify({"error": "PIN and Confirm PIN do not match."}), 400
    try:
        pin_hash = hashlib.sha256(data['pin'].encode()).hexdigest()
        now = datetime.utcnow()
        user = User(
            phone_number=data['phone'],
            name=data['full_name'],
            pin_hash=pin_hash,
            role='nurse',
            created_at=now,
            updated_at=now
        )
        db.session.add(user)
        db.session.flush()
        nurse = Nurse(
            user_id=user.id,
            nurse_name=data['full_name'],
            license_number=data['license_number'],
            location=data['location'],
            created_at=now
        )
        db.session.add(nurse)
        db.session.commit()
        logging.error(f"[NURSE REGISTER] Success for phone: {data['phone']}")
        return jsonify({"message": "Nurse registered successfully", "nurse_id": nurse.id}), 201
    except Exception as e:
        db.session.rollback()
        logging.error(f"[NURSE REGISTER] Exception: {str(e)}")
        return jsonify({"error": str(e)}), 500

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
        "phone": user.phone_number,
        "license_number": nurse.license_number,
        "location": nurse.location,
        "created_at": nurse.created_at.isoformat()
    }), 200

@bp.route('/nurses/<int:nurse_id>', methods=['PUT'])
def update_nurse(nurse_id):
    nurse = Nurse.query.get(nurse_id)
    if not nurse:
        return jsonify({"error": "Nurse not found."}), 404
    data = request.get_json()
    user = User.query.get(nurse.user_id)
    if 'full_name' in data:
        nurse.nurse_name = data['full_name']
        user.name = data['full_name']
    if 'license_number' in data:
        nurse.license_number = data['license_number']
    if 'location' in data:
        nurse.location = data['location']
    db.session.commit()
    return jsonify({"message": "Nurse profile updated successfully."}), 200

@bp.route('/nurses/<int:nurse_id>', methods=['DELETE'])
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
            "phone": user.phone_number,
            "license_number": nurse.license_number,
            "location": nurse.location,
            "created_at": nurse.created_at.isoformat()
        })
    return jsonify({"nurses": result}), 200
