"""
routes_weight.py
────────────────
Weight log CRUD for mothers.

  POST   /mothers/me/weight         – mother logs her weight
  GET    /mothers/me/weight         – mother lists own weight history
  GET    /mothers/<id>/weight       – CHW/Nurse views a mother's weight log
"""

from flask import Blueprint, request, jsonify
from models import db, WeightLog, Mother
from models_standard import MotherCHWAssignment
from auth_utils import require_auth, get_current_user
from datetime import datetime, timedelta, timezone

bp = Blueprint('weight', __name__)


@bp.route('/mothers/me/weight', methods=['POST'])
@require_auth
def log_my_weight():
    """Mother logs her own weight."""
    user = get_current_user()
    mother = Mother.query.filter_by(user_id=user.id).first()
    if not mother:
        return jsonify({'error': 'Mother profile not found.'}), 404

    data = request.get_json() or {}
    weight_kg = data.get('weight_kg')
    if weight_kg is None:
        return jsonify({'error': 'weight_kg is required.'}), 400

    try:
        weight_kg = float(weight_kg)
        if weight_kg <= 0 or weight_kg > 300:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({'error': 'weight_kg must be a positive number.'}), 400

    # Auto-calculate week number from due date
    week_number = data.get('week_number')
    if week_number is None and mother.due_date:
        today = datetime.now(timezone.utc).date()
        conception = mother.due_date - timedelta(days=280)
        days_pregnant = (today - conception).days
        week_number = max(1, min(42, days_pregnant // 7))

    entry = WeightLog(
        mother_id=mother.id,
        weight_kg=weight_kg,
        week_number=week_number,
        notes=data.get('notes', '').strip() or None,
        recorded_by=user.id,
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(entry)
    db.session.commit()

    return jsonify({
        'message': 'Weight logged.',
        **_serialize(entry),
    }), 201


@bp.route('/mothers/me/weight', methods=['GET'])
@require_auth
def get_my_weight():
    """Mother views her own weight history."""
    user = get_current_user()
    mother = Mother.query.filter_by(user_id=user.id).first()
    if not mother:
        return jsonify({'error': 'Mother profile not found.'}), 404

    logs = (WeightLog.query
            .filter_by(mother_id=mother.id)
            .order_by(WeightLog.created_at.desc())
            .all())

    return jsonify([_serialize(w) for w in logs]), 200


@bp.route('/mothers/<int:mother_id>/weight', methods=['GET'])
@require_auth
def get_mother_weight(mother_id):
    """CHW/Nurse views a specific mother's weight log."""
    user = get_current_user()
    mother = Mother.query.get(mother_id)
    if not mother:
        return jsonify({'error': 'Mother not found.'}), 404

    if not _can_access_mother(user, mother):
        return jsonify({'error': "Forbidden. You are not authorized to access this mother's weight records."}), 403

    logs = (WeightLog.query
            .filter_by(mother_id=mother_id)
            .order_by(WeightLog.created_at.desc())
            .all())

    return jsonify([_serialize(w) for w in logs]), 200


def _can_access_mother(user, mother: Mother) -> bool:
    """Role + assignment/ward authorization for mother-specific records."""
    if not user:
        return False

    if user.role == 'chw':
        if not user.chw:
            return False
        assignment = MotherCHWAssignment.query.filter_by(
            chw_id=user.chw.id,
            mother_id=mother.id,
            status='active'
        ).first()
        return assignment is not None

    if user.role == 'nurse':
        if not user.nurse:
            return False
        # Nurses are limited to mothers in their ward.
        return user.nurse.ward_id == mother.ward_id

    return False


def _serialize(w):
    return {
        'id': w.id,
        'mother_id': w.mother_id,
        'weight_kg': float(w.weight_kg),
        'week_number': w.week_number,
        'notes': w.notes,
        'recorded_by': w.recorded_by,
        'created_at': w.created_at.isoformat() if w.created_at else None,
    }
