"""
routes_checkin.py
─────────────────
Daily check-in CRUD for the RemyCareConnect app.

  POST   /mothers/<mother_id>/checkins          – mother submits check-in
  GET    /mothers/<mother_id>/checkins          – list check-ins for a mother (newest first)
  GET    /mothers/<mother_id>/checkins/latest   – single most-recent check-in
  GET    /chws/<chw_id>/checkins                – all recent check-ins for CHW's assigned mothers
"""

from flask import Blueprint, request, jsonify
from models import db, DailyCheckin, Mother, CHW, User, DailyCheckinHiddenForUser
from models_standard import MotherCHWAssignment
from auth_utils import require_auth, get_current_user
from sqlalchemy import desc
from datetime import datetime, timezone, timedelta
from socket_manager import socketio
from notifications import create_user_notification

bp = Blueprint('checkin', __name__)

VALID_RESPONSES = ('ok', 'not_ok')
VALID_CHANNELS  = ('app', 'whatsapp', 'sms')
HIDDEN_RETENTION_DAYS = 15


def _serialize(c, mother_name: str | None = None):
    return {
        "id":          c.id,
        "mother_id":   c.mother_id,
        "mother_name": mother_name or (c.mother.mother_name if c.mother else None),
        "response":    c.response,
        "comment":     c.comment,
        "symptoms":    c.symptoms or [],
        "channel":     c.channel,
        "created_at":  c.created_at.isoformat() if c.created_at else None,
    }


# ── Submit check-in ────────────────────────────────────────────────────────────
@bp.route('/mothers/<int:mother_id>/checkins', methods=['POST'])
@require_auth
def create_checkin(mother_id):
    """
    Request body:
      { "response": "ok" | "not_ok", "comment": "<optional>", "channel": "app" }
    """
    mother = Mother.query.get(mother_id)
    if not mother:
        return jsonify({"error": "Mother not found."}), 404

    data = request.get_json() or {}

    response = data.get('response', '').strip().lower()
    if response not in VALID_RESPONSES:
        return jsonify({"error": f"response must be one of {VALID_RESPONSES}."}), 400

    channel = data.get('channel', 'app').strip().lower()
    if channel not in VALID_CHANNELS:
        channel = 'app'

    # Parse optional symptoms list
    symptoms = data.get('symptoms', [])
    if not isinstance(symptoms, list):
        symptoms = []
    # Sanitize: only keep non-empty strings
    symptoms = [s.strip() for s in symptoms if isinstance(s, str) and s.strip()]

    checkin = DailyCheckin(
        mother_id=mother_id,
        response=response,
        comment=data.get('comment', '').strip() or None,
        symptoms=symptoms,
        channel=channel,
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(checkin)
    db.session.commit()

    payload = {
        "message": "Check-in recorded.",
        **_serialize(checkin, mother.mother_name),
    }

    # ── WebSocket push ──────────────────────────────────────────────────────
    # 1. Notify the mother's own personal room
    socketio.emit("checkin:new", payload, to=f"user:{mother.user_id}")
    # 2. Notify the assigned CHW(s) via their profile room and user room
    assignment = MotherCHWAssignment.query.filter_by(
        mother_id=mother_id, status='active'
    ).first()
    if assignment:
        socketio.emit("checkin:new", payload, to=f"chw:{assignment.chw_id}")
        # Also emit to the CHW's user room for reliability (reconnect safety)
        chw = CHW.query.get(assignment.chw_id)
        if chw:
            socketio.emit("checkin:new", payload, to=f"user:{chw.user_id}")
            create_user_notification(
                user_id=chw.user_id,
                event_type="checkin:new",
                title="New Daily Check-in",
                message=f"Check-in received from {mother.mother_name}.",
                url="/dashboard/chw",
                entity_type="checkin",
                entity_id=checkin.id,
            )
    # ───────────────────────────────────────────────────────────────────────

    return jsonify(payload), 201


# ── List check-ins for a mother ────────────────────────────────────────────────
@bp.route('/mothers/<int:mother_id>/checkins', methods=['GET'])
@require_auth
def list_checkins(mother_id):
    mother = Mother.query.get(mother_id)
    if not mother:
        return jsonify({"error": "Mother not found."}), 404

    limit = min(int(request.args.get('limit', 30)), 100)
    checkins = (DailyCheckin.query
                .filter_by(mother_id=mother_id)
                .order_by(desc(DailyCheckin.created_at))
                .limit(limit)
                .all())

    return jsonify({
        "checkins": [_serialize(c, mother.mother_name) for c in checkins],
        "total":    len(checkins),
    }), 200


# ── Latest check-in for a mother ──────────────────────────────────────────────
@bp.route('/mothers/<int:mother_id>/checkins/latest', methods=['GET'])
@require_auth
def latest_checkin(mother_id):
    mother = Mother.query.get(mother_id)
    if not mother:
        return jsonify({"error": "Mother not found."}), 404

    checkin = (DailyCheckin.query
               .filter_by(mother_id=mother_id)
               .order_by(desc(DailyCheckin.created_at))
               .first())

    if not checkin:
        return jsonify({"checkin": None}), 200

    return jsonify({"checkin": _serialize(checkin, mother.mother_name)}), 200


# ── All recent check-ins for a CHW's assigned mothers ─────────────────────────
@bp.route('/chws/<int:chw_id>/checkins', methods=['GET'])
@require_auth
def chw_checkins(chw_id):
    """
    Returns the most recent check-ins (default: last 50) across all mothers
    currently assigned to this CHW, ordered newest first.
    ?deleted_only=true  – show only soft-deleted for current user
    ?include_deleted=true – include soft-deleted
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({"error": "Unauthorized."}), 401

    limit = min(int(request.args.get('limit', 50)), 200)
    include_deleted = str(request.args.get('include_deleted', 'false')).lower() in ('1', 'true', 'yes')
    deleted_only = str(request.args.get('deleted_only', 'false')).lower() in ('1', 'true', 'yes')
    cutoff = datetime.now(timezone.utc) - timedelta(days=HIDDEN_RETENTION_DAYS)

    # Get all active mother IDs assigned to this CHW
    assignments = (MotherCHWAssignment.query
                   .filter_by(chw_id=chw_id, status='active')
                   .all())
    mother_ids = [a.mother_id for a in assignments]

    if not mother_ids:
        return jsonify({"checkins": [], "total": 0}), 200

    q = (DailyCheckin.query
         .filter(DailyCheckin.mother_id.in_(mother_ids)))

    if deleted_only:
        hidden_subq = db.session.query(DailyCheckinHiddenForUser.checkin_id).filter(
            DailyCheckinHiddenForUser.user_id == current_user.id,
            DailyCheckinHiddenForUser.hidden_at >= cutoff,
        )
        q = q.filter(DailyCheckin.id.in_(hidden_subq))
    elif not include_deleted:
        hidden_subq = db.session.query(DailyCheckinHiddenForUser.checkin_id).filter_by(user_id=current_user.id)
        q = q.filter(~DailyCheckin.id.in_(hidden_subq))

    checkins = (q.order_by(desc(DailyCheckin.created_at))
                .limit(limit)
                .all())

    # Pre-fetch mother names to avoid N+1
    mothers = {m.id: m for m in Mother.query.filter(Mother.id.in_(mother_ids)).all()}

    return jsonify({
        "checkins": [
            _serialize(c, mothers.get(c.mother_id, Mother()).mother_name)
            for c in checkins
        ],
        "total": len(checkins),
    }), 200


# ── Soft-delete check-in (per-user) ──────────────────────────────────────────

@bp.route('/checkins/<int:checkin_id>/delete', methods=['POST'])
@require_auth
def soft_delete_checkin(checkin_id):
    """Remove from the current user's dashboard (non-destructive, per-user)."""
    current_user = get_current_user()
    if not current_user:
        return jsonify({"error": "Unauthorized."}), 401

    checkin = DailyCheckin.query.get(checkin_id)
    if not checkin:
        return jsonify({"error": "Check-in not found."}), 404

    # A CHW can hide any check-in from their assigned mothers.
    # A mother can hide their own check-ins.
    is_mother_of_checkin = current_user.mother and current_user.mother.id == checkin.mother_id
    is_assigned_chw = False
    if current_user.chw:
        assignment = MotherCHWAssignment.query.filter_by(
            mother_id=checkin.mother_id, chw_id=current_user.chw.id, status='active'
        ).first()
        is_assigned_chw = assignment is not None

    if not is_mother_of_checkin and not is_assigned_chw:
        return jsonify({"error": "Forbidden. You can only hide your own check-ins or those of assigned mothers."}), 403

    existing = DailyCheckinHiddenForUser.query.filter_by(
        checkin_id=checkin_id, user_id=current_user.id
    ).first()
    if existing:
        existing.hidden_at = datetime.now(timezone.utc)
        db.session.commit()
        return jsonify({"message": "Check-in already deleted from your dashboard.", "checkin_id": checkin_id}), 200

    hidden = DailyCheckinHiddenForUser()
    hidden.checkin_id = checkin_id
    hidden.user_id = current_user.id
    hidden.reason = (request.get_json(silent=True) or {}).get('reason')
    db.session.add(hidden)
    db.session.commit()

    payload = {"id": checkin_id, "user_id": current_user.id}
    socketio.emit("checkin:deleted", payload, to=f"user:{current_user.id}")
    return jsonify({"message": "Check-in deleted from your dashboard.", "checkin_id": checkin_id}), 200


@bp.route('/checkins/<int:checkin_id>/delete', methods=['DELETE'])
@require_auth
def restore_checkin(checkin_id):
    """Restore a previously soft-deleted check-in for the current user."""
    current_user = get_current_user()
    if not current_user:
        return jsonify({"error": "Unauthorized."}), 401

    hidden = DailyCheckinHiddenForUser.query.filter_by(
        checkin_id=checkin_id, user_id=current_user.id
    ).first()
    if not hidden:
        return jsonify({"message": "Check-in is not deleted from your dashboard."}), 200

    cutoff = datetime.now(timezone.utc) - timedelta(days=HIDDEN_RETENTION_DAYS)
    hidden_at = hidden.hidden_at if hidden.hidden_at.tzinfo else hidden.hidden_at.replace(tzinfo=timezone.utc)
    if hidden_at < cutoff:
        return jsonify({
            "error": f"Restore window expired. Deleted check-ins are restorable for {HIDDEN_RETENTION_DAYS} days only.",
        }), 410

    db.session.delete(hidden)
    db.session.commit()

    payload = {"id": checkin_id, "user_id": current_user.id}
    socketio.emit("checkin:restored", payload, to=f"user:{current_user.id}")
    return jsonify({"message": "Check-in restored to your dashboard."}), 200
