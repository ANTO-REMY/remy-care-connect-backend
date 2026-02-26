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
from models import db, CHW, Nurse, Mother, Escalation
from auth_utils import require_auth, require_role, get_current_user
from datetime import datetime

bp = Blueprint('escalations', __name__)

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
            created_at=datetime.utcnow(),
        )
        db.session.add(escalation)
        db.session.commit()
        return jsonify({"message": "Escalation created.", **_serialize(escalation)}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# ── List escalations ──────────────────────────────────────────────────────────

@bp.route('/escalations', methods=['GET'])
def list_escalations():
    """
    List escalations.  Optional query params:
      ?nurse_id=  ?chw_id=  ?mother_id=  ?status=  ?priority=
    """
    q = Escalation.query
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
        e.resolved_at = datetime.utcnow()
    if notes := data.get('notes'):
        e.notes = notes

    db.session.commit()
    return jsonify({"message": f"Escalation status updated to '{new_status}'.",
                    **_serialize(e)}), 200

# ── Update escalation fields ──────────────────────────────────────────────────

@bp.route('/escalations/<int:escalation_id>', methods=['PATCH'])
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
    return jsonify({"message": "Escalation updated.", **_serialize(e)}), 200

# ── Delete escalation ─────────────────────────────────────────────────────────

@bp.route('/escalations/<int:escalation_id>', methods=['DELETE'])
def delete_escalation(escalation_id):
    e = Escalation.query.get(escalation_id)
    if not e:
        return jsonify({"error": "Escalation not found."}), 404
    db.session.delete(e)
    db.session.commit()
    return jsonify({"message": "Escalation deleted."}), 200
