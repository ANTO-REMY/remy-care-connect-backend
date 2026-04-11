"""
routes_ultrasound.py
────────────────────
Ultrasound record CRUD.

  POST   /mothers/<id>/ultrasound   – CHW/Nurse records scan data
  GET    /mothers/<id>/ultrasound   – list ultrasound records for a mother
  GET    /mothers/me/ultrasound     – mother views own ultrasound records
"""

from flask import Blueprint, request, jsonify
from models import db, UltrasoundRecord, Mother, CHW
from models_standard import MotherCHWAssignment
from auth_utils import require_auth, get_current_user
from datetime import datetime, timezone
from socket_manager import socketio
from notifications import create_user_notification

bp = Blueprint('ultrasound', __name__)


@bp.route('/mothers/me/ultrasound', methods=['GET'])
@require_auth
def get_my_ultrasound():
    """Mother views her own ultrasound records."""
    user = get_current_user()
    mother = Mother.query.filter_by(user_id=user.id).first()
    if not mother:
        return jsonify({'error': 'Mother profile not found.'}), 404

    records = (UltrasoundRecord.query
               .filter_by(mother_id=mother.id)
               .order_by(UltrasoundRecord.scan_date.desc())
               .all())

    return jsonify([_serialize(r) for r in records]), 200


@bp.route('/mothers/<int:mother_id>/ultrasound', methods=['GET'])
@require_auth
def get_mother_ultrasound(mother_id):
    """List ultrasound records for an authorized CHW/Nurse."""
    user = get_current_user()
    mother = Mother.query.get(mother_id)
    if not mother:
        return jsonify({'error': 'Mother not found.'}), 404

    if not _can_access_mother(user, mother):
        return jsonify({'error': "Forbidden. You are not authorized to access this mother's ultrasound records."}), 403

    records = (UltrasoundRecord.query
               .filter_by(mother_id=mother_id)
               .order_by(UltrasoundRecord.scan_date.desc())
               .all())

    return jsonify([_serialize(r) for r in records]), 200


@bp.route('/mothers/<int:mother_id>/ultrasound', methods=['POST'])
@require_auth
def create_ultrasound(mother_id):
    """CHW or Nurse records ultrasound scan data for a mother."""
    user = get_current_user()

    # Only CHW or Nurse can record ultrasound data
    if user.role not in ('chw', 'nurse'):
        return jsonify({'error': 'Only CHW or Nurse can record ultrasound data.'}), 403

    mother = Mother.query.get(mother_id)
    if not mother:
        return jsonify({'error': 'Mother not found.'}), 404

    data = request.get_json() or {}

    week_number = data.get('week_number')
    scan_date = data.get('scan_date')

    if not week_number or not scan_date:
        return jsonify({'error': 'week_number and scan_date are required.'}), 400

    try:
        week_number = int(week_number)
        if week_number < 1 or week_number > 42:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({'error': 'week_number must be between 1 and 42.'}), 400

    try:
        parsed_date = datetime.strptime(scan_date, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'scan_date must be in YYYY-MM-DD format.'}), 400

    record = UltrasoundRecord(
        mother_id=mother_id,
        week_number=week_number,
        fetal_weight_grams=data.get('fetal_weight_grams'),
        fetal_length_cm=data.get('fetal_length_cm'),
        heart_rate_bpm=data.get('heart_rate_bpm'),
        notes=data.get('notes', '').strip() or None,
        recorded_by=user.id,
        scan_date=parsed_date,
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(record)
    db.session.commit()
    _emit_ultrasound_created(record, mother, user)

    return jsonify({
        'message': 'Ultrasound record saved.',
        **_serialize(record),
    }), 201


def _serialize(r):
    return {
        'id': r.id,
        'mother_id': r.mother_id,
        'week_number': r.week_number,
        'fetal_weight_grams': float(r.fetal_weight_grams) if r.fetal_weight_grams else None,
        'fetal_length_cm': float(r.fetal_length_cm) if r.fetal_length_cm else None,
        'heart_rate_bpm': r.heart_rate_bpm,
        'notes': r.notes,
        'recorded_by': r.recorded_by,
        'scan_date': r.scan_date.isoformat() if r.scan_date else None,
        'created_at': r.created_at.isoformat() if r.created_at else None,
    }


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


def _emit_ultrasound_created(record: UltrasoundRecord, mother: Mother, actor_user) -> None:
    """Emit ultrasound realtime updates + persist in-app notifications."""
    payload = _serialize(record)

    # Mother-facing update
    socketio.emit("ultrasound:created", payload, to=f"user:{mother.user_id}")
    create_user_notification(
        user_id=mother.user_id,
        event_type="ultrasound:created",
        title="New Ultrasound Record",
        message="A new ultrasound measurement has been added to your care record.",
        url="/dashboard/mother",
        entity_type="ultrasound_record",
        entity_id=record.id,
    )

    # Assigned CHW update (room + user room, dual-room delivery)
    assignment = MotherCHWAssignment.query.filter_by(
        mother_id=mother.id,
        status='active'
    ).first()
    if not assignment:
        return

    socketio.emit("ultrasound:created", payload, to=f"chw:{assignment.chw_id}")
    chw = CHW.query.get(assignment.chw_id)
    if not chw:
        return

    socketio.emit("ultrasound:created", payload, to=f"user:{chw.user_id}")
    if actor_user and actor_user.id != chw.user_id:
        create_user_notification(
            user_id=chw.user_id,
            event_type="ultrasound:created",
            title="Mother Ultrasound Updated",
            message=f"New ultrasound recorded for {mother.mother_name}.",
            url="/dashboard/chw",
            entity_type="ultrasound_record",
            entity_id=record.id,
        )
