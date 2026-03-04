"""
routes_appointments.py
======================
CRUD for AppointmentSchedule records.

Relationships:
  mother_id       → users.id  (a user with role='mother')
  health_worker_id → users.id  (a user with role='chw' or 'nurse')

Endpoints:
  POST   /appointments            – create
  GET    /appointments            – list (filterable)
  GET    /appointments/<id>       – get single
  PATCH  /appointments/<id>       – update
  PATCH  /appointments/<id>/status – update status only
  DELETE /appointments/<id>       – delete
"""

from flask import Blueprint, jsonify, request
from models import db, AppointmentSchedule, User, Mother, CHW, Nurse
from models_standard import MotherCHWAssignment
from auth_utils import require_auth, require_role, get_current_user
from datetime import datetime, timezone
from socket_manager import socketio

bp = Blueprint('appointments', __name__)

# ── Serialiser ────────────────────────────────────────────────────────────────

def _serialize(a):
    return {
        "id": a.id,
        "mother_id": a.mother_id,
        "health_worker_id": a.health_worker_id,
        "created_by_user_id": a.created_by_user_id,
        "scheduled_time": a.scheduled_time.isoformat() if a.scheduled_time else None,
        "appointment_type": a.appointment_type,
        "recurrence_rule": a.recurrence_rule,
        "recurrence_end": a.recurrence_end.isoformat() if a.recurrence_end else None,
        "status": a.status,
        "escalated": a.escalated,
        "escalation_reason": a.escalation_reason,
        "notes": a.notes,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }

# ── Validate participants ─────────────────────────────────────────────────────

def _get_user_or_error(user_id, label):
    user = User.query.get(user_id)
    if not user:
        return None, jsonify({"error": f"{label} with id {user_id} not found."}), 404
    return user, None, None

def _emit_appointment_event(event_name, payload, mother_id, health_worker_id):
    """Helper to emit WebSocket events to both user and profile rooms."""
    socketio.emit(event_name, payload, to=f"user:{mother_id}")
    socketio.emit(event_name, payload, to=f"user:{health_worker_id}")

    chw_profile = CHW.query.filter_by(user_id=health_worker_id).first()
    if chw_profile:
        socketio.emit(event_name, payload, to=f"chw:{chw_profile.id}")

    nurse_profile = Nurse.query.filter_by(user_id=health_worker_id).first()
    if nurse_profile:
        socketio.emit(event_name, payload, to=f"nurse:{nurse_profile.id}")

# ── Create appointment ────────────────────────────────────────────────────────

@bp.route('/appointments', methods=['POST'])
@require_auth
def create_appointment():
    """
    Create an appointment.
    Body:
      mother_id (int), health_worker_id (int), scheduled_time (ISO8601) – required
      status ('scheduled'|'completed'|'cancelled'|'rescheduled') – optional, default 'scheduled'
      recurrence_rule (str, optional), recurrence_end (ISO8601, optional),
      notes (str, optional)
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({"error": "Unauthorized."}), 401

    data = request.get_json() or {}

    required = ['mother_id', 'health_worker_id', 'scheduled_time']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    status = data.get('status', 'scheduled')
    if status == 'cancelled':
        status = 'canceled'
    if status not in ('scheduled', 'completed', 'canceled', 'rescheduled'):
        return jsonify({"error": "status must be scheduled | completed | canceled | rescheduled"}), 400

    # Validate mother user exists
    mother_user = User.query.get(data['mother_id'])
    if not mother_user:
        return jsonify({"error": f"User (mother) {data['mother_id']} not found."}), 404

    # If current user is a mother, auto-resolve to their assigned CHW
    final_health_worker_id = data['health_worker_id']
    if current_user.role == 'mother':
        # Lookup mother profile by user_id
        mother_profile = Mother.query.filter_by(user_id=current_user.id).first()
        if mother_profile:
            # Find active CHW assignment
            assignment = MotherCHWAssignment.query.filter_by(
                mother_id=mother_profile.id, status='active'
            ).first()
            if assignment:
                # Get CHW profile to find their user_id
                chw_profile = CHW.query.get(assignment.chw_id)
                if chw_profile:
                    final_health_worker_id = chw_profile.user_id

    # Validate health worker user exists
    hw_user = User.query.get(final_health_worker_id)
    if not hw_user:
        return jsonify({"error": f"User (health worker) {final_health_worker_id} not found."}), 404

    # Parse scheduled_time
    try:
        scheduled_time = datetime.fromisoformat(data['scheduled_time'].replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return jsonify({"error": "scheduled_time must be a valid ISO 8601 datetime."}), 400

    recurrence_end = None
    if data.get('recurrence_end'):
        try:
            recurrence_end = datetime.fromisoformat(data['recurrence_end'].replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return jsonify({"error": "recurrence_end must be a valid ISO 8601 datetime."}), 400

    now = datetime.now(timezone.utc)
    try:
        appt = AppointmentSchedule()
        appt.mother_id = data['mother_id']
        appt.health_worker_id = final_health_worker_id  # Use resolved health worker ID
        appt.scheduled_time = scheduled_time
        appt.recurrence_rule = data.get('recurrence_rule')
        appt.recurrence_end = recurrence_end
        appt.appointment_type = data.get('appointment_type')
        appt.status = status
        appt.escalated = data.get('escalated', False)
        appt.escalation_reason = data.get('escalation_reason')
        appt.notes = data.get('notes')
        appt.created_by_user_id = current_user.id  # Track who created this
        appt.created_at = now
        appt.updated_at = now
        db.session.add(appt)
        db.session.commit()

        payload = {"message": "Appointment created.", **_serialize(appt)}
        _emit_appointment_event("appointment:created", payload, appt.mother_id, appt.health_worker_id)
        return jsonify(payload), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# ── List appointments ─────────────────────────────────────────────────────────

@bp.route('/appointments', methods=['GET'])
def list_appointments():
    """
    Filter by: ?mother_id= ?health_worker_id= ?status= ?from= ?to=
    from / to are ISO8601 dates to bound scheduled_time.
    """
    q = AppointmentSchedule.query
    if mother_id := request.args.get('mother_id', type=int):
        q = q.filter_by(mother_id=mother_id)
    if hw_id := request.args.get('health_worker_id', type=int):
        q = q.filter_by(health_worker_id=hw_id)
    if status := request.args.get('status'):
        q = q.filter_by(status=status)
    if from_str := request.args.get('from'):
        try:
            from_dt = datetime.fromisoformat(from_str.replace('Z', '+00:00'))
            q = q.filter(AppointmentSchedule.scheduled_time >= from_dt)
        except ValueError:
            return jsonify({"error": "Invalid 'from' datetime."}), 400
    if to_str := request.args.get('to'):
        try:
            to_dt = datetime.fromisoformat(to_str.replace('Z', '+00:00'))
            q = q.filter(AppointmentSchedule.scheduled_time <= to_dt)
        except ValueError:
            return jsonify({"error": "Invalid 'to' datetime."}), 400

    appts = q.order_by(AppointmentSchedule.scheduled_time).all()
    return jsonify({
        "appointments": [_serialize(a) for a in appts],
        "total": len(appts),
    }), 200

# ── Get single appointment ────────────────────────────────────────────────────

@bp.route('/appointments/<int:appt_id>', methods=['GET'])
def get_appointment(appt_id):
    a = AppointmentSchedule.query.get(appt_id)
    if not a:
        return jsonify({"error": "Appointment not found."}), 404
    return jsonify(_serialize(a)), 200

# ── Update appointment ────────────────────────────────────────────────────────

@bp.route('/appointments/<int:appt_id>', methods=['PATCH'])
@require_auth
def update_appointment(appt_id):
    """Update mutable fields: scheduled_time, notes, recurrence_rule, recurrence_end"""
    a = AppointmentSchedule.query.get(appt_id)
    if not a:
        return jsonify({"error": "Appointment not found."}), 404

    data = request.get_json() or {}

    if 'scheduled_time' in data:
        try:
            a.scheduled_time = datetime.fromisoformat(data['scheduled_time'].replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return jsonify({"error": "scheduled_time must be a valid ISO 8601 datetime."}), 400

    for field in ('notes', 'recurrence_rule', 'escalation_reason', 'appointment_type'):
        if field in data:
            setattr(a, field, data[field])

    if 'escalated' in data:
        a.escalated = bool(data['escalated'])
    if 'recurrence_end' in data:
        try:
            a.recurrence_end = datetime.fromisoformat(data['recurrence_end'].replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return jsonify({"error": "recurrence_end must be a valid ISO 8601 datetime."}), 400

    a.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    payload = {"message": "Appointment updated.", **_serialize(a)}
    _emit_appointment_event("appointment:updated", payload, a.mother_id, a.health_worker_id)
    return jsonify(payload), 200

# ── Update status only ────────────────────────────────────────────────────────

@bp.route('/appointments/<int:appt_id>/status', methods=['PATCH'])
@require_auth
def update_appointment_status(appt_id):
    """
    Body: { "status": "scheduled" | "completed" | "cancelled" | "rescheduled" }
    """
    a = AppointmentSchedule.query.get(appt_id)
    if not a:
        return jsonify({"error": "Appointment not found."}), 404

    data = request.get_json() or {}
    new_status = data.get('status')
    if new_status == 'cancelled':
        new_status = 'canceled'
    if new_status not in ('scheduled', 'completed', 'canceled', 'rescheduled'):
        return jsonify({"error": "status must be scheduled | completed | canceled | rescheduled"}), 400

    a.status = new_status
    a.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    payload = {"message": f"Appointment status updated to '{new_status}'.", **_serialize(a)}
    _emit_appointment_event("appointment:updated", payload, a.mother_id, a.health_worker_id)
    return jsonify(payload), 200

# ── Delete appointment ────────────────────────────────────────────────────────

@bp.route('/appointments/<int:appt_id>', methods=['DELETE'])
@require_auth
def delete_appointment(appt_id):
    a = AppointmentSchedule.query.get(appt_id)
    if not a:
        return jsonify({"error": "Appointment not found."}), 404
    # Capture IDs before deletion for the WS event
    mother_id = a.mother_id
    hw_id = a.health_worker_id
    appt_id_val = a.id
    db.session.delete(a)
    db.session.commit()
    # ── WebSocket push ────────────────────────────────────────────────────
    payload = {"id": appt_id_val}
    socketio.emit("appointment:deleted", payload, to=f"user:{mother_id}")
    socketio.emit("appointment:deleted", payload, to=f"user:{hw_id}")
    chw_profile = CHW.query.filter_by(user_id=hw_id).first()
    if chw_profile:
        socketio.emit("appointment:deleted", payload, to=f"chw:{chw_profile.id}")
    nurse_profile = Nurse.query.filter_by(user_id=hw_id).first()
    if nurse_profile:
        socketio.emit("appointment:deleted", payload, to=f"nurse:{nurse_profile.id}")
    # ─────────────────────────────────────────────────────────────────────
    return jsonify({"message": "Appointment deleted."}), 200
