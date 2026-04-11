from flask import Blueprint, request, jsonify
from models import db, NextOfKin, Mother
from auth_utils import require_auth, get_current_user
from datetime import datetime, timezone

bp = Blueprint('nextofkin', __name__)

@bp.route('/nextofkin', methods=['POST'])
@require_auth
def create_next_of_kin():
    user = get_current_user()

    # Resolve the mothers table PK from the current user's ID
    mother = Mother.query.filter_by(user_id=user.id).first()
    if not mother:
        return jsonify({'error': 'Mother profile not found. Please complete your profile first.'}), 404

    data = request.get_json()
    required = ['name', 'phone', 'sex', 'relationship']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400

    kin = NextOfKin(
        user_id=mother.id,                          # FK → mothers.id  ✓
        mother_name=mother.mother_name or user.name,
        name=data['name'],
        phone=data['phone'],
        sex=data['sex'],
        relationship=data['relationship'],
        created_at=datetime.now(timezone.utc)
    )
    db.session.add(kin)
    db.session.commit()
    return jsonify({'message': 'Next of kin added', 'id': kin.id}), 201


@bp.route('/nextofkin/me', methods=['GET'])
@require_auth
def get_my_next_of_kin():
    """Return next-of-kin for the currently authenticated mother (resolved from JWT)."""
    user = get_current_user()
    mother = Mother.query.filter_by(user_id=user.id).first()
    if not mother:
        return jsonify({'error': 'Mother profile not found.'}), 404
    kin_list = NextOfKin.query.filter_by(user_id=mother.id).all()
    return jsonify([
        {
            'id': k.id,
            'user_id': k.user_id,
            'mother_name': k.mother_name,
            'name': k.name,
            'phone': k.phone,
            'sex': k.sex,
            'relationship': k.relationship,
            'created_at': k.created_at.isoformat()
        } for k in kin_list
    ]), 200


@bp.route('/nextofkin/<int:mother_id>', methods=['GET'])
def get_next_of_kin(mother_id):
    kin_list = NextOfKin.query.filter_by(user_id=mother_id).all()
    return jsonify([
        {
            'id': k.id,
            'user_id': k.user_id,
            'mother_name': k.mother_name,
            'name': k.name,
            'phone': k.phone,
            'sex': k.sex,
            'relationship': k.relationship,
            'created_at': k.created_at.isoformat()
        } for k in kin_list
    ]), 200

@bp.route('/nextofkin/<int:kin_id>', methods=['PUT'])
def update_next_of_kin(kin_id):
    kin = NextOfKin.query.get(kin_id)
    if not kin:
        return jsonify({'error': 'Next of kin not found'}), 404
    data = request.get_json()
    for field in ['name', 'phone', 'sex', 'relationship']:
        if field in data:
            setattr(kin, field, data[field])
    db.session.commit()
    return jsonify({'message': 'Next of kin updated'}), 200

@bp.route('/nextofkin/<int:kin_id>', methods=['DELETE'])
def delete_next_of_kin(kin_id):
    kin = NextOfKin.query.get(kin_id)
    if not kin:
        return jsonify({'error': 'Next of kin not found'}), 404
    db.session.delete(kin)
    db.session.commit()
    return jsonify({'message': 'Next of kin deleted'}), 200
