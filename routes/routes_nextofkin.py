from flask import Blueprint, request, jsonify
from models import db, NextOfKin, Mother
from datetime import datetime

bp = Blueprint('nextofkin', __name__)

@bp.route('/nextofkin/', methods=['POST'])
def create_next_of_kin():
    data = request.get_json()
    required = ['user_id', 'mother_name', 'name', 'phone', 'sex', 'relationship']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    kin = NextOfKin(
        user_id=data['user_id'],
        mother_name=data['mother_name'],
        name=data['name'],
        phone=data['phone'],
        sex=data['sex'],
        relationship=data['relationship'],
        created_at=datetime.utcnow()
    )
    db.session.add(kin)
    db.session.commit()
    return jsonify({'message': 'Next of kin added', 'id': kin.id}), 201

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

@bp.route('/logout', methods=['POST'])
def logout():
    # For stateless APIs, client should just delete token. Here for completeness.
    return jsonify({'message': 'Logged out successfully.'}), 200
