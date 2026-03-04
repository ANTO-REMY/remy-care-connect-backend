"""
routes/socket_events.py
───────────────────────
Socket.IO connection lifecycle and room-management events.

Connection flow
───────────────
1. Client connects with  ?token=<JWT>  in the query string.
2. Server verifies the token; on success the socket is put into:
     • user:{user_id}   – personal room
     • role:{role}      – broad role room (mother / chw / nurse)
3. Client then emits  join_rooms  with   { "profile_id": <int> }
   to additionally enter the typed-profile room:
     • chw:{chw_profile_id}    or
     • nurse:{nurse_profile_id}
   (mothers don't need a separate profile room currently)

All event names the server can push to clients
──────────────────────────────────────────────
  checkin:new              payload: serialised CheckIn dict
  appointment:created      payload: serialised Appointment dict
  appointment:updated      payload: serialised Appointment dict
  appointment:deleted      payload: { id }
  escalation:created       payload: serialised Escalation dict
  escalation:updated       payload: serialised Escalation dict
  escalation:deleted       payload: { id }
  assignment:created       payload: serialised Assignment dict
  assignment:status_changed payload: serialised Assignment dict
  assignment:deleted       payload: { id, chw_id, mother_id }
  mother:profile_updated   payload: mother profile dict
  chw:profile_updated      payload: CHW profile dict
  nurse:profile_updated    payload: nurse profile dict
"""

from flask import request
from flask_socketio import join_room, leave_room, emit
from flask_jwt_extended import decode_token
from jwt.exceptions import DecodeError, ExpiredSignatureError

from socket_manager import socketio
from models import (
    db, AppointmentSchedule, Escalation, CHW, Nurse, Mother, User,
)
from models_standard import MotherCHWAssignment
from datetime import datetime, timezone, timedelta


# ── connect ───────────────────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    """
    Authenticates the socket connection using the JWT passed as
    the `token` query-string parameter, then joins the socket into
    its personal and role rooms.
    """
    token = request.args.get("token", "")
    if not token:
        # Reject unauthenticated connections
        return False  # disconnect

    try:
        decoded = decode_token(token)
        identity = decoded.get("sub", {})

        # identity may be a dict (our custom identity) or just an int/str
        if isinstance(identity, dict):
            user_id = identity.get("id") or identity.get("user_id")
            role    = identity.get("role", "")
        else:
            # Fallback: store raw identity; role rooms won't be set
            user_id = identity
            role    = ""

        if not user_id:
            return False

        # Personal room
        join_room(f"user:{user_id}")
        # Role room
        if role:
            join_room(f"role:{role}")

        # Persist for later events
        request.environ["_ws_user_id"] = user_id
        request.environ["_ws_role"]    = role

    except (DecodeError, ExpiredSignatureError, Exception):
        return False  # reject


# ── join_rooms ────────────────────────────────────────────────────────────────

@socketio.on("join_rooms")
def on_join_rooms(data):
    """
    Client sends { "profile_id": <int> } after connecting to enter
    the typed-profile room (chw:<id> or nurse:<id>).
    Re-decodes JWT from request.args since request.environ is not
    shared across socket events in threading mode.
    """
    token = request.args.get("token", "")
    profile_id = data.get("profile_id") if isinstance(data, dict) else None

    if not token or not profile_id:
        return

    try:
        decoded = decode_token(token)
        identity = decoded.get("sub", {})
        if isinstance(identity, dict):
            role = identity.get("role", "")
        else:
            role = ""

        if role in ("chw", "nurse"):
            join_room(f"{role}:{profile_id}")
    except (DecodeError, ExpiredSignatureError, Exception):
        pass  # Silently fail — socket will continue without profile room


# ── disconnect ────────────────────────────────────────────────────────────────

@socketio.on("disconnect")
def on_disconnect():
    pass  # Flask-SocketIO cleans up rooms automatically


# ── request_sync ──────────────────────────────────────────────────────────────

def _appt_serialize(a):
    return {
        "id": a.id,
        "mother_id": a.mother_id,
        "health_worker_id": a.health_worker_id,
        "created_by_user_id": a.created_by_user_id,
        "scheduled_time": a.scheduled_time.isoformat() if a.scheduled_time else None,
        "appointment_type": a.appointment_type,
        "status": a.status,
        "notes": a.notes,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


def _escalation_serialize(e):
    return {
        "id": e.id,
        "chw_id": e.chw_id,
        "chw_name": e.chw_name,
        "nurse_id": e.nurse_id,
        "nurse_name": e.nurse_name,
        "mother_id": e.mother_id,
        "mother_name": e.mother_name,
        "case_description": e.case_description,
        "issue_type": e.issue_type,
        "notes": e.notes,
        "priority": e.priority,
        "status": e.status,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "resolved_at": e.resolved_at.isoformat() if e.resolved_at else None,
    }


@socketio.on("request_sync")
def on_request_sync(data):
    """
    Client emits this on reconnect to catch up on missed events.
    Payload: { "role": "mother"|"chw"|"nurse", "user_id": int, "profile_id": int|null }

    Server responds with a `sync` event containing the latest state snapshot
    relevant to the caller's role so the client can reconcile.
    """
    if not isinstance(data, dict):
        return

    token = request.args.get("token", "")
    if not token:
        return

    try:
        decoded = decode_token(token)
    except (DecodeError, ExpiredSignatureError, Exception):
        return

    identity = decoded.get("sub", {})
    if isinstance(identity, dict):
        user_id = identity.get("id") or identity.get("user_id")
        role = identity.get("role", "")
    else:
        user_id = identity
        role = ""

    if not user_id:
        return

    payload = {"role": role, "user_id": user_id}

    try:
        if role == "mother":
            # Appointments where mother_id = user_id
            appts = AppointmentSchedule.query.filter_by(mother_id=user_id).all()
            payload["appointments"] = [_appt_serialize(a) for a in appts]

        elif role == "chw":
            profile_id = data.get("profile_id")
            if profile_id:
                # Appointments where health_worker_id = user_id
                appts = AppointmentSchedule.query.filter_by(health_worker_id=user_id).all()
                payload["appointments"] = [_appt_serialize(a) for a in appts]
                # Escalations where chw_id = profile_id
                escs = Escalation.query.filter_by(chw_id=profile_id).all()
                payload["escalations"] = [_escalation_serialize(e) for e in escs]
                # Active assignments
                assigns = MotherCHWAssignment.query.filter_by(
                    chw_id=profile_id, status="active"
                ).all()
                payload["assignments"] = [{
                    "id": a.id, "mother_id": a.mother_id,
                    "mother_name": a.mother_name, "status": a.status,
                } for a in assigns]

        elif role == "nurse":
            profile_id = data.get("profile_id")
            if profile_id:
                # Appointments where health_worker_id = user_id
                appts = AppointmentSchedule.query.filter_by(health_worker_id=user_id).all()
                payload["appointments"] = [_appt_serialize(a) for a in appts]
                # Escalations where nurse_id = profile_id
                escs = Escalation.query.filter_by(nurse_id=profile_id).all()
                payload["escalations"] = [_escalation_serialize(e) for e in escs]

    except Exception:
        pass  # Partial payload is fine

    emit("sync", payload)
