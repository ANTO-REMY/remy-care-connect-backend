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
    DELETE /appointments/<id>       – hard delete (disabled)
"""

from flask import Blueprint, jsonify, request
from sqlalchemy import or_
from models import db, AppointmentSchedule, AppointmentHiddenForUser, User, Mother, CHW, Nurse
from models_standard import MotherCHWAssignment
from auth_utils import require_auth, require_role, get_current_user
from datetime import datetime, timezone, timedelta
from socket_manager import socketio
from notifications import send_push, create_user_notification
from push_payloads import build_push_data

bp = Blueprint('appointments', __name__)
HIDDEN_RETENTION_DAYS = 15

# ── Serialiser ────────────────────────────────────────────────────────────────

def _serialize(a):
    creator_name = a.creator_user.name if a.creator_user else None
    creator_role = a.creator_user.role if a.creator_user else None
    return {
        "id": a.id,
        "mother_id": a.mother_id,
        "health_worker_id": a.health_worker_id,
        "created_by_user_id": a.created_by_user_id,
        "mother_name": a.mother_user.name if a.mother_user else None,
        "hw_name": a.hw_user.name if a.hw_user else None,
        "creator_name": creator_name,
        "creator_role": creator_role,
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
    """Helper to emit WebSocket events and Push Notifications to participants."""
    socketio.emit(event_name, payload, to=f"user:{mother_id}")
    socketio.emit(event_name, payload, to=f"user:{health_worker_id}")
    
    # Try sending Push Notifications (skip sending to the user who triggered the action)
    current = get_current_user()
    current_uid = current.id if current else None
    appointment_id = payload.get("id")
    hw_user = User.query.get(health_worker_id)
    hw_role = hw_user.role if hw_user else None
    hw_url = "/dashboard/nurse" if hw_role == 'nurse' else "/dashboard/chw"
    
    msg = payload.get("message", "You have an appointment update.")
    if mother_id != current_uid:
        create_user_notification(
            user_id=mother_id,
            event_type=event_name,
            title="Appointment Update",
            message=msg,
            url="/dashboard/mother",
            entity_type="appointment",
            entity_id=appointment_id,
        )
        send_push(
            mother_id,
            "Appointment Update",
            msg,
            data=build_push_data(
                event=event_name,
                url="/dashboard/mother",
                entity_type="appointment",
                entity_id=appointment_id,
                role="mother",
            ),
        )
    if health_worker_id != current_uid:
        create_user_notification(
            user_id=health_worker_id,
            event_type=event_name,
            title="Appointment Update",
            message=msg,
            url=hw_url,
            entity_type="appointment",
            entity_id=appointment_id,
        )
        send_push(
            health_worker_id,
            "Appointment Update",
            msg,
            data=build_push_data(
                event=event_name,
                url=hw_url,
                entity_type="appointment",
                entity_id=appointment_id,
                role=hw_role or "chw",
            ),
        )

    chw_profile = CHW.query.filter_by(user_id=health_worker_id).first()
    if chw_profile:
        socketio.emit(event_name, payload, to=f"chw:{chw_profile.id}")

    nurse_profile = Nurse.query.filter_by(user_id=health_worker_id).first()
    if nurse_profile:
        socketio.emit(event_name, payload, to=f"nurse:{nurse_profile.id}")
        
        # If a nurse creates/updates an appointment, notify the assigned CHW
        mother_profile = Mother.query.filter_by(user_id=mother_id).first()
        if mother_profile:
            assignment = MotherCHWAssignment.query.filter_by(
                mother_id=mother_profile.id, 
                status='active'
            ).first()
            if assignment:
                socketio.emit(event_name, payload, to=f"chw:{assignment.chw_id}")
                # Also emit to the CHW's user room for reliability
                assigned_chw = CHW.query.get(assignment.chw_id)
                if assigned_chw:
                    socketio.emit(event_name, payload, to=f"user:{assigned_chw.user_id}")
                    if assigned_chw.user_id != current_uid:
                        create_user_notification(
                            user_id=assigned_chw.user_id,
                            event_type=event_name,
                            title="Nurse Appointment Update",
                            message=f"Nurse Update: {msg}",
                            url="/dashboard/chw",
                            entity_type="appointment",
                            entity_id=appointment_id,
                        )
                        send_push(
                            assigned_chw.user_id,
                            "Nurse Appointment Update",
                            f"Nurse Update: {msg}",
                            data=build_push_data(
                                event=event_name,
                                url="/dashboard/chw",
                                entity_type="appointment",
                                entity_id=appointment_id,
                                role="chw",
                            ),
                        )


def _can_manage_appointment(current_user, appointment):
    """Only related users can manage visibility/deletion for an appointment."""
    if not current_user or not appointment:
        return False
    return current_user.id in {
        appointment.mother_id,
        appointment.health_worker_id,
        appointment.created_by_user_id,
    }


def _apply_appointment_scope(query, current_user):
    """Restrict reads to appointments the current user is involved in."""
    if current_user.role == 'mother':
        return query.filter(
            or_(
                AppointmentSchedule.mother_id == current_user.id,
                AppointmentSchedule.created_by_user_id == current_user.id,
            )
        )
    if current_user.role in ('chw', 'nurse'):
        return query.filter(
            or_(
                AppointmentSchedule.health_worker_id == current_user.id,
                AppointmentSchedule.created_by_user_id == current_user.id,
            )
        )
    return query.filter(AppointmentSchedule.id == -1)

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
    if status not in ('scheduled', 'completed', 'canceled'):
        return jsonify({"error": "status must be scheduled | completed | canceled"}), 400

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
@require_auth
def list_appointments():
    """
    Filter by: ?mother_id= ?health_worker_id= ?status= ?from= ?to=
    from / to are ISO8601 dates to bound scheduled_time.
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({"error": "Unauthorized."}), 401

    q = _apply_appointment_scope(AppointmentSchedule.query, current_user)
    include_hidden = str(request.args.get('include_hidden', 'false')).lower() in ('1', 'true', 'yes')
    hidden_only = str(request.args.get('hidden_only', 'false')).lower() in ('1', 'true', 'yes')
    include_deleted = str(request.args.get('include_deleted', 'false')).lower() in ('1', 'true', 'yes')
    deleted_only = str(request.args.get('deleted_only', 'false')).lower() in ('1', 'true', 'yes')
    include_hidden = include_hidden or include_deleted
    hidden_only = hidden_only or deleted_only
    cutoff = datetime.now(timezone.utc) - timedelta(days=HIDDEN_RETENTION_DAYS)

    if hidden_only:
        hidden_subq = db.session.query(AppointmentHiddenForUser.appointment_id).filter(
            AppointmentHiddenForUser.user_id == current_user.id,
            AppointmentHiddenForUser.hidden_at >= cutoff,
        )
        q = q.filter(AppointmentSchedule.id.in_(hidden_subq))
    elif not include_hidden:
        hidden_subq = db.session.query(AppointmentHiddenForUser.appointment_id).filter_by(user_id=current_user.id)
        q = q.filter(~AppointmentSchedule.id.in_(hidden_subq))
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
@require_auth
def get_appointment(appt_id):
    current_user = get_current_user()
    if not current_user:
        return jsonify({"error": "Unauthorized."}), 401

    a = AppointmentSchedule.query.get(appt_id)
    if not a:
        return jsonify({"error": "Appointment not found."}), 404
    if not _can_manage_appointment(current_user, a):
        return jsonify({"error": "Forbidden."}), 403
    return jsonify(_serialize(a)), 200

# ── Update appointment ────────────────────────────────────────────────────────

@bp.route('/appointments/<int:appt_id>', methods=['PATCH'])
@require_auth
def update_appointment(appt_id):
    """Update mutable fields: scheduled_time, notes, recurrence_rule, recurrence_end"""
    current_user = get_current_user()
    if not current_user:
        return jsonify({"error": "Unauthorized."}), 401

    a = AppointmentSchedule.query.get(appt_id)
    if not a:
        return jsonify({"error": "Appointment not found."}), 404
    if not _can_manage_appointment(current_user, a):
        return jsonify({"error": "Forbidden."}), 403

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
    Body: { "status": "scheduled" | "completed" | "canceled" }
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({"error": "Unauthorized."}), 401

    a = AppointmentSchedule.query.get(appt_id)
    if not a:
        return jsonify({"error": "Appointment not found."}), 404
    if not _can_manage_appointment(current_user, a):
        return jsonify({"error": "Forbidden."}), 403

    data = request.get_json() or {}
    new_status = data.get('status')
    if new_status == 'cancelled':
        new_status = 'canceled'
    if new_status not in ('scheduled', 'completed', 'canceled'):
        return jsonify({"error": "status must be scheduled | completed | canceled"}), 400

    a.status = new_status
    a.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    payload = {"message": f"Appointment status updated to '{new_status}'.", **_serialize(a)}
    _emit_appointment_event("appointment:updated", payload, a.mother_id, a.health_worker_id)
    return jsonify(payload), 200


@bp.route('/appointments/<int:appt_id>/hide', methods=['POST'])
@bp.route('/appointments/<int:appt_id>/delete', methods=['POST'])
@require_auth
def hide_appointment(appt_id):
    current_user = get_current_user()
    if not current_user:
        return jsonify({"error": "Unauthorized."}), 401

    a = AppointmentSchedule.query.get(appt_id)
    if not a:
        return jsonify({"error": "Appointment not found."}), 404
    if not _can_manage_appointment(current_user, a):
        return jsonify({"error": "Forbidden."}), 403

    existing = AppointmentHiddenForUser.query.filter_by(
        appointment_id=appt_id,
        user_id=current_user.id,
    ).first()
    if existing:
        existing.hidden_at = datetime.now(timezone.utc)
        existing.reason = (request.get_json(silent=True) or {}).get('reason') or existing.reason
        db.session.commit()
        return jsonify({"message": "Appointment already deleted from your dashboard.", "appointment_id": appt_id}), 200

    hidden = AppointmentHiddenForUser()
    hidden.appointment_id = appt_id
    hidden.user_id = current_user.id
    hidden.reason = (request.get_json(silent=True) or {}).get('reason')
    db.session.add(hidden)
    db.session.commit()

    payload = {"id": appt_id, "user_id": current_user.id}
    socketio.emit("appointment:hidden", payload, to=f"user:{current_user.id}")
    socketio.emit("appointment:deleted", payload, to=f"user:{current_user.id}")
    return jsonify({"message": "Appointment deleted from your dashboard.", "appointment_id": appt_id}), 200


@bp.route('/appointments/<int:appt_id>/hide', methods=['DELETE'])
@bp.route('/appointments/<int:appt_id>/delete', methods=['DELETE'])
@require_auth
def unhide_appointment(appt_id):
    current_user = get_current_user()
    if not current_user:
        return jsonify({"error": "Unauthorized."}), 401

    a = AppointmentSchedule.query.get(appt_id)
    if not a:
        return jsonify({"error": "Appointment not found."}), 404
    if not _can_manage_appointment(current_user, a):
        return jsonify({"error": "Forbidden."}), 403

    hidden = AppointmentHiddenForUser.query.filter_by(
        appointment_id=appt_id,
        user_id=current_user.id,
    ).first()
    if not hidden:
        return jsonify({"message": "Appointment is not deleted from your dashboard.", "appointment_id": appt_id}), 200

    cutoff = datetime.now(timezone.utc) - timedelta(days=HIDDEN_RETENTION_DAYS)
    hidden_at = hidden.hidden_at if hidden.hidden_at.tzinfo else hidden.hidden_at.replace(tzinfo=timezone.utc)
    if hidden_at < cutoff:
        return jsonify({
            "error": f"Restore window expired. Deleted appointments are restorable for {HIDDEN_RETENTION_DAYS} days only.",
            "appointment_id": appt_id,
        }), 410

    db.session.delete(hidden)
    db.session.commit()
    payload = {"id": appt_id, "user_id": current_user.id}
    socketio.emit("appointment:restored", payload, to=f"user:{current_user.id}")
    return jsonify({"message": "Appointment restored to your dashboard.", "appointment_id": appt_id}), 200

# ── Delete appointment ────────────────────────────────────────────────────────

@bp.route('/appointments/<int:appt_id>', methods=['DELETE'])
@require_auth
def delete_appointment(appt_id):
    return jsonify({
        "error": "Hard delete is disabled for appointments.",
        "message": "Use POST /appointments/<id>/delete to remove it from your dashboard.",
    }), 405
