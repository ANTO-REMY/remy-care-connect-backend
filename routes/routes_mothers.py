from flask import Blueprint, request, jsonify
from models import db, User, Mother
from auth_utils import require_auth, require_role, get_current_user
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError

bp = Blueprint('mothers', __name__)

@bp.route('/mothers/me', methods=['GET'])
@require_auth
def get_my_mother_profile():
    """Return the mother profile for the currently authenticated user."""
    user = get_current_user()
    mother = Mother.query.filter_by(user_id=user.id).first()
    if not mother:
        return jsonify({"error": "Mother profile not found."}), 404
    return jsonify({
        "mother_id": mother.id,
        "user_id":   user.id,
        "name":      mother.mother_name,
        "first_name": user.first_name,
        "last_name":  user.last_name,
        "dob":        mother.dob.strftime('%Y-%m-%d'),
        "due_date":   mother.due_date.strftime('%Y-%m-%d'),
        "location":   mother.location,
        "phone":      user.phone_number,
    }), 200

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
            created_at=datetime.now(timezone.utc)
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
        "first_name": user.first_name,
        "last_name": user.last_name,
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
        parts = data['full_name'].strip().split(' ', 1)
        user = User.query.get(mother.user_id)
        user.first_name = parts[0]
        user.last_name  = parts[1] if len(parts) > 1 else ''
        mother.mother_name = data['full_name'].strip()
        updated = True
    elif 'first_name' in data or 'last_name' in data:
        user = User.query.get(mother.user_id)
        if 'first_name' in data:
            user.first_name = data['first_name'].strip()
        if 'last_name' in data:
            user.last_name = data['last_name'].strip()
        mother.mother_name = user.name
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
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to update profile: {str(e)}"}), 500
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
