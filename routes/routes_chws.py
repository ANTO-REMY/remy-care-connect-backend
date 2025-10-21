from flask import Blueprint, request, jsonify
from models import db, User, CHW
from auth_utils import require_auth, require_role, get_current_user
from datetime import datetime

bp = Blueprint('chws', __name__)

import logging

@bp.route('/chws/register', methods=['POST'])
def register_chw():
    data = request.get_json()
    logging.error(f"[CHW REGISTER] {request.method} {request.path} - DATA: {data}")
    required_fields = ['full_name', 'phone', 'license_number', 'location', 'pin', 'confirm_pin']
    for field in required_fields:
        if not data.get(field):
            logging.error(f"[CHW REGISTER] Missing field: {field}")
            return jsonify({"error": f"{field} is required."}), 400
    if User.query.filter_by(phone_number=data['phone']).first():
        logging.error(f"[CHW REGISTER] Phone number already registered: {data['phone']}")
        return jsonify({"error": "Phone number already registered."}), 409
    if data['pin'] != data['confirm_pin']:
        logging.error("[CHW REGISTER] PIN and Confirm PIN do not match.")
        return jsonify({"error": "PIN and Confirm PIN do not match."}), 400
    try:
        pin_hash = hashlib.sha256(data['pin'].encode()).hexdigest()
        now = datetime.utcnow()
        user = User(
            phone_number=data['phone'],
            name=data['full_name'],
            pin_hash=pin_hash,
            role='chw',
            created_at=now,
            updated_at=now
        )
        db.session.add(user)
        db.session.flush()
        chw = CHW(
            user_id=user.id,
            chw_name=data['full_name'],
            license_number=data['license_number'],
            location=data['location'],
            created_at=now
        )
        db.session.add(chw)
        db.session.commit()
        logging.error(f"[CHW REGISTER] Success for phone: {data['phone']}")
        return jsonify({"message": "CHW registered successfully", "chw_id": chw.id}), 201
    except Exception as e:
        db.session.rollback()
        logging.error(f"[CHW REGISTER] Exception: {str(e)}")
        return jsonify({"error": str(e)}), 500

@bp.route('/chws/<int:chw_id>', methods=['GET'])
def get_chw(chw_id):
    chw = CHW.query.get(chw_id)
    if not chw:
        return jsonify({"error": "CHW not found."}), 404
    user = User.query.get(chw.user_id)
    return jsonify({
        "chw_id": chw.id,
        "user_id": user.id,
        "name": chw.chw_name,
        "phone": user.phone_number,
        "license_number": chw.license_number,
        "location": chw.location,
        "created_at": chw.created_at.isoformat()
    }), 200

@bp.route('/chws/<int:chw_id>', methods=['PUT'])
def update_chw(chw_id):
    chw = CHW.query.get(chw_id)
    if not chw:
        return jsonify({"error": "CHW not found."}), 404
    data = request.get_json()
    user = User.query.get(chw.user_id)
    if 'full_name' in data:
        chw.chw_name = data['full_name']
        user.name = data['full_name']
    if 'license_number' in data:
        chw.license_number = data['license_number']
    if 'location' in data:
        chw.location = data['location']
    db.session.commit()
    return jsonify({"message": "CHW profile updated successfully."}), 200

@bp.route('/chws/<int:chw_id>', methods=['DELETE'])
def delete_chw(chw_id):
    chw = CHW.query.get(chw_id)
    if not chw:
        return jsonify({"error": "CHW not found."}), 404
    user = User.query.get(chw.user_id)
    db.session.delete(chw)
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "CHW profile deleted successfully."}), 200

@bp.route('/chws', methods=['GET'])
def list_chws():
    chws = CHW.query.all()
    result = []
    for chw in chws:
        user = User.query.get(chw.user_id)
        result.append({
            "chw_id": chw.id,
            "user_id": user.id,
            "name": chw.chw_name,
            "phone": user.phone_number,
            "license_number": chw.license_number,
            "location": chw.location,
            "created_at": chw.created_at.isoformat()
        })
    return jsonify({"chws": result}), 200
