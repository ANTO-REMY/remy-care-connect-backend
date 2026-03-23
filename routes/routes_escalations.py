"""
routes_escalations.py
=====================
CRUD for Escalation records.

Escalation flow:
  1. CHW creates an escalation (POST /escalations)
  2. Nurse lists & filters escalations assigned to them (GET /escalations)
  3. Nurse updates status: pending → in_progress → resolved/rejected
     (PATCH /escalations/<id>/status)
  4. Either party can fetch a single escalation (GET /escalations/<id>)
"""

from flask import Blueprint, jsonify, request
from models import db, CHW, Nurse, Mother, Escalation, EscalationHiddenForUser
from auth_utils import require_auth, require_role, get_current_user
from datetime import datetime, timezone, timedelta
from socket_manager import socketio

bp = Blueprint('escalations', __name__)
HIDDEN_RETENTION_DAYS = 15

# ── WebSocket helper ──────────────────────────────────────────────────────────

def _emit_escalation_event(event: str, payload: dict, chw_id: int, nurse_id: int, chw=None, nurse=None):
    """Emit to CHW profile room, nurse profile room, and both user rooms (dual-room pattern)."""
    socketio.emit(event, payload, to=f"chw:{chw_id}")
    socketio.emit(event, payload, to=f"nurse:{nurse_id}")
    if chw is None:
        chw = CHW.query.get(chw_id)
    if nurse is None:
        nurse = Nurse.query.get(nurse_id)
    if chw:
        socketio.emit(event, payload, to=f"user:{chw.user_id}")
    if nurse:
        socketio.emit(event, payload, to=f"user:{nurse.user_id}")

# ── Serialiser ────────────────────────────────────────────────────────────────

def _serialize(e):
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

# ── Create escalation ─────────────────────────────────────────────────────────

@bp.route('/escalations', methods=['POST'])
@require_auth
def create_escalation():
    """
    CHW submits an escalation.
    Body:
      chw_id, nurse_id, mother_id, case_description,
      issue_type (optional), notes (optional), priority (default 'medium')
    """
    data = request.get_json() or {}

    required = ['chw_id', 'nurse_id', 'mother_id', 'case_description']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    chw = CHW.query.get(data['chw_id'])
    if not chw:
        return jsonify({"error": f"CHW {data['chw_id']} not found."}), 404

    nurse = Nurse.query.get(data['nurse_id'])
    if not nurse:
        return jsonify({"error": f"Nurse {data['nurse_id']} not found."}), 404

    mother = Mother.query.get(data['mother_id'])
    if not mother:
        return jsonify({"error": f"Mother {data['mother_id']} not found."}), 404

    priority = data.get('priority', 'medium')
    if priority not in ('low', 'medium', 'high', 'critical'):
        return jsonify({"error": "priority must be low | medium | high | critical"}), 400

    try:
        escalation = Escalation(
            chw_id=chw.id,
            chw_name=chw.chw_name,
            nurse_id=nurse.id,
            nurse_name=nurse.nurse_name,
            mother_id=mother.id,
            mother_name=mother.mother_name,
            case_description=data['case_description'],
            issue_type=data.get('issue_type'),
            notes=data.get('notes'),
            priority=priority,
            status='pending',
            created_at=datetime.now(timezone.utc),
        )
        db.session.add(escalation)
        db.session.commit()

        payload = {"message": "Escalation created.", **_serialize(escalation)}
        # ── WebSocket push (all 4 rooms: profile + user for both CHW and nurse) ──
        _emit_escalation_event("escalation:created", payload, escalation.chw_id, escalation.nurse_id, chw=chw, nurse=nurse)
        # ──────────────────────────────────────────────────────────────────────
        return jsonify(payload), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# ── List escalations ──────────────────────────────────────────────────────────

@bp.route('/escalations', methods=['GET'])
@require_auth
def list_escalations():
    """
    List escalations.  Optional query params:
      ?nurse_id=  ?chw_id=  ?mother_id=  ?status=  ?priority=
      ?deleted_only=true  – show only soft-deleted for current user
      ?include_deleted=true – include soft-deleted
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({"error": "Unauthorized."}), 401

    include_deleted = str(request.args.get('include_deleted', 'false')).lower() in ('1', 'true', 'yes')
    deleted_only = str(request.args.get('deleted_only', 'false')).lower() in ('1', 'true', 'yes')
    cutoff = datetime.now(timezone.utc) - timedelta(days=HIDDEN_RETENTION_DAYS)

    q = Escalation.query
    if deleted_only:
        hidden_subq = db.session.query(EscalationHiddenForUser.escalation_id).filter(
            EscalationHiddenForUser.user_id == current_user.id,
            EscalationHiddenForUser.hidden_at >= cutoff,
        )
        q = q.filter(Escalation.id.in_(hidden_subq))
    elif not include_deleted:
        hidden_subq = db.session.query(EscalationHiddenForUser.escalation_id).filter_by(user_id=current_user.id)
        q = q.filter(~Escalation.id.in_(hidden_subq))

    if nurse_id := request.args.get('nurse_id', type=int):
        q = q.filter_by(nurse_id=nurse_id)
    if chw_id := request.args.get('chw_id', type=int):
        q = q.filter_by(chw_id=chw_id)
    if mother_id := request.args.get('mother_id', type=int):
        q = q.filter_by(mother_id=mother_id)
    if status := request.args.get('status'):
        q = q.filter_by(status=status)
    if priority := request.args.get('priority'):
        q = q.filter_by(priority=priority)

    escalations = q.order_by(Escalation.created_at.desc()).all()
    return jsonify({
        "escalations": [_serialize(e) for e in escalations],
        "total": len(escalations),
    }), 200

# ── Get single escalation ─────────────────────────────────────────────────────

@bp.route('/escalations/<int:escalation_id>', methods=['GET'])
def get_escalation(escalation_id):
    e = Escalation.query.get(escalation_id)
    if not e:
        return jsonify({"error": "Escalation not found."}), 404
    return jsonify(_serialize(e)), 200

# ── Update status (nurse action) ──────────────────────────────────────────────

@bp.route('/escalations/<int:escalation_id>/status', methods=['PATCH'])
@require_auth
@require_role('nurse')
def update_escalation_status(escalation_id):
    """
    Nurse updates the status.
    Body: { "status": "in_progress" | "resolved" | "rejected", "notes": "..." }
    Sets resolved_at automatically when status is resolved/rejected.
    """
    e = Escalation.query.get(escalation_id)
    if not e:
        return jsonify({"error": "Escalation not found."}), 404

    data = request.get_json() or {}
    new_status = data.get('status')
    if new_status not in ('pending', 'in_progress', 'resolved', 'rejected'):
        return jsonify({
            "error": "status must be pending | in_progress | resolved | rejected"
        }), 400

    e.status = new_status
    if new_status in ('resolved', 'rejected'):
        e.resolved_at = datetime.now(timezone.utc)
    if notes := data.get('notes'):
        e.notes = notes

    db.session.commit()

    payload = {"message": f"Escalation status updated to '{new_status}'.", **_serialize(e)}
    # ── WebSocket push (all 4 rooms) ──────────────────────────────────────
    _emit_escalation_event("escalation:updated", payload, e.chw_id, e.nurse_id)
    # ──────────────────────────────────────────────────────────────────────
    return jsonify(payload), 200

# ── Update escalation fields ──────────────────────────────────────────────────

@bp.route('/escalations/<int:escalation_id>', methods=['PATCH'])
@require_auth
def update_escalation(escalation_id):
    """
    Update mutable fields: notes, priority, issue_type, case_description.
    """
    e = Escalation.query.get(escalation_id)
    if not e:
        return jsonify({"error": "Escalation not found."}), 404

    data = request.get_json() or {}
    allowed = ('notes', 'priority', 'issue_type', 'case_description')
    for field in allowed:
        if field in data:
            setattr(e, field, data[field])

    if 'priority' in data and data['priority'] not in ('low', 'medium', 'high', 'critical'):
        return jsonify({"error": "priority must be low | medium | high | critical"}), 400

    db.session.commit()

    payload = {"message": "Escalation updated.", **_serialize(e)}
    # ── WebSocket push (all 4 rooms) ──────────────────────────────────────
    _emit_escalation_event("escalation:updated", payload, e.chw_id, e.nurse_id)
    # ──────────────────────────────────────────────────────────────────────
    return jsonify(payload), 200

# ── Soft-delete escalation (per-user) ────────────────────────────────────────

@bp.route('/escalations/<int:escalation_id>/delete', methods=['POST'])
@require_auth
def soft_delete_escalation(escalation_id):
    """Remove from the current user's dashboard (non-destructive, per-user)."""
    current_user = get_current_user()
    if not current_user:
        return jsonify({"error": "Unauthorized."}), 401

    e = Escalation.query.get(escalation_id)
    if not e:
        return jsonify({"error": "Escalation not found."}), 404

    # Only the CHW (user_id) or nurse (user_id) involved can hide it
    chw = CHW.query.get(e.chw_id)
    nurse = Nurse.query.get(e.nurse_id)
    allowed_user_ids = set()
    if chw:
        allowed_user_ids.add(chw.user_id)
    if nurse:
        allowed_user_ids.add(nurse.user_id)
    if current_user.id not in allowed_user_ids:
        return jsonify({"error": "Forbidden."}), 403

    existing = EscalationHiddenForUser.query.filter_by(
        escalation_id=escalation_id, user_id=current_user.id
    ).first()
    if existing:
        existing.hidden_at = datetime.now(timezone.utc)
        existing.reason = (request.get_json(silent=True) or {}).get('reason') or existing.reason
        db.session.commit()
        return jsonify({"message": "Escalation already deleted from your dashboard.", "escalation_id": escalation_id}), 200

    hidden = EscalationHiddenForUser()
    hidden.escalation_id = escalation_id
    hidden.user_id = current_user.id
    hidden.reason = (request.get_json(silent=True) or {}).get('reason')
    db.session.add(hidden)
    db.session.commit()

    payload = {"id": escalation_id, "user_id": current_user.id}
    socketio.emit("escalation:deleted", payload, to=f"user:{current_user.id}")
    return jsonify({"message": "Escalation deleted from your dashboard.", "escalation_id": escalation_id}), 200


@bp.route('/escalations/<int:escalation_id>/delete', methods=['DELETE'])
@require_auth
def restore_escalation(escalation_id):
    """Restore a previously soft-deleted escalation for current user."""
    current_user = get_current_user()
    if not current_user:
        return jsonify({"error": "Unauthorized."}), 401

    e = Escalation.query.get(escalation_id)
    if not e:
        return jsonify({"error": "Escalation not found."}), 404

    hidden = EscalationHiddenForUser.query.filter_by(
        escalation_id=escalation_id, user_id=current_user.id
    ).first()
    if not hidden:
        return jsonify({"message": "Escalation is not deleted from your dashboard.", "escalation_id": escalation_id}), 200

    cutoff = datetime.now(timezone.utc) - timedelta(days=HIDDEN_RETENTION_DAYS)
    hidden_at = hidden.hidden_at if hidden.hidden_at.tzinfo else hidden.hidden_at.replace(tzinfo=timezone.utc)
    if hidden_at < cutoff:
        return jsonify({
            "error": f"Restore window expired. Deleted escalations are restorable for {HIDDEN_RETENTION_DAYS} days only.",
            "escalation_id": escalation_id,
        }), 410

    db.session.delete(hidden)
    db.session.commit()
    return jsonify({"message": "Escalation restored to your dashboard.", "escalation_id": escalation_id}), 200


# ── Hard-delete (disabled) ────────────────────────────────────────────────────

@bp.route('/escalations/<int:escalation_id>', methods=['DELETE'])
@require_auth
def delete_escalation(escalation_id):
    """Hard delete disabled — use POST /escalations/<id>/delete instead."""
    return jsonify({
        "error": "Hard delete is disabled for escalations.",
        "message": "Use POST /escalations/<id>/delete to remove it from your dashboard.",
    }), 405
