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
  checkin:new          payload: serialised CheckIn dict
  appointment:created  payload: serialised Appointment dict
  appointment:updated  payload: serialised Appointment dict
  escalation:created   payload: serialised Escalation dict
  escalation:updated   payload: serialised Escalation dict
"""

from flask import request
from flask_socketio import join_room, leave_room, emit
from flask_jwt_extended import decode_token
from jwt.exceptions import DecodeError, ExpiredSignatureError

from socket_manager import socketio


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
    """
    role       = request.environ.get("_ws_role", "")
    profile_id = data.get("profile_id") if isinstance(data, dict) else None

    if profile_id and role in ("chw", "nurse"):
        join_room(f"{role}:{profile_id}")


# ── disconnect ────────────────────────────────────────────────────────────────

@socketio.on("disconnect")
def on_disconnect():
    pass  # Flask-SocketIO cleans up rooms automatically
