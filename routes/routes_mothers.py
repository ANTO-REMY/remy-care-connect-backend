from flask import Blueprint, request, jsonify
from models import db, User, Mother
from auth_utils import require_auth, require_role, get_current_user
from datetime import datetime
from sqlalchemy.exc import IntegrityError

bp = Blueprint('mothers', __name__)

@bp.route('/mothers/complete-profile', methods=['POST'])
@require_auth
@require_role('mother')
def complete_mother_profile():
    """Complete mother profile after registration and verification"""
    user = get_current_user()
    
    # Check if profile already exists
    if user.mother:
        return jsonify({"error": "Mother profile already exists"}), 409
    
    data = request.get_json()
    required_fields = ['dob', 'due_date', 'location']
    for field in required_fields:
        if not data.get(field):
            return jsonify({"error": f"{field} is required."}), 400
    
    try:
        mother = Mother(
            user_id=user.id,
            mother_name=user.name,
            dob=datetime.strptime(data['dob'], '%Y-%m-%d'),
            due_date=datetime.strptime(data['due_date'], '%Y-%m-%d'),
            location=data['location'],
            created_at=datetime.utcnow()
        )
        db.session.add(mother)
        db.session.commit()
        return jsonify({"message": "Mother profile completed successfully", "mother_id": mother.id}), 201
    except ValueError as e:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@bp.route('/mothers/<int:mother_id>', methods=['GET'])
@require_auth
def get_mother_profile(mother_id):
    mother = Mother.query.get(mother_id)
    if not mother:
        return jsonify({"error": "Mother not found."}), 404
    user = User.query.get(mother.user_id)
    return jsonify({
        "mother_id": mother.id,
        "user_id": user.id,
        "name": mother.mother_name,
        "dob": mother.dob.strftime('%Y-%m-%d'),
        "due_date": mother.due_date.strftime('%Y-%m-%d'),
        "location": mother.location,
        "phone": user.phone_number
    }), 200

@bp.route('/mothers/<int:mother_id>', methods=['PUT'])
@require_auth
def update_mother_profile(mother_id):
    mother = Mother.query.get(mother_id)
    if not mother:
        return jsonify({"error": "Mother not found."}), 404
    data = request.get_json()
    updated = False
    if 'full_name' in data and data['full_name']:
        mother.mother_name = data['full_name']
        user = User.query.get(mother.user_id)
        user.name = data['full_name']
        updated = True
    if 'dob' in data and data['dob']:
        try:
            mother.dob = datetime.strptime(data['dob'], '%Y-%m-%d')
            updated = True
        except Exception:
            return jsonify({"error": "Invalid dob format. Use YYYY-MM-DD."}), 400
    if 'due_date' in data and data['due_date']:
        try:
            mother.due_date = datetime.strptime(data['due_date'], '%Y-%m-%d')
            updated = True
        except Exception:
            return jsonify({"error": "Invalid due_date format. Use YYYY-MM-DD."}), 400
    if 'location' in data and data['location']:
        mother.location = data['location']
        updated = True
    if not updated:
        return jsonify({"error": "No valid fields to update."}), 400
    db.session.commit()
    return jsonify({"message": "Mother profile updated successfully."}), 200

@bp.route('/mothers/<int:mother_id>', methods=['DELETE'])
@require_auth
@require_role('nurse', 'chw')
def delete_mother_profile(mother_id):
    mother = Mother.query.get(mother_id)
    if not mother:
        return jsonify({"error": "Mother not found."}), 404
    user = User.query.get(mother.user_id)
    db.session.delete(mother)
    if user:
        db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "Mother profile deleted successfully."}), 200
