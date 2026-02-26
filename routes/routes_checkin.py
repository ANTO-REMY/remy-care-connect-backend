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
from models import db, DailyCheckin, Mother, User
from models_standard import MotherCHWAssignment
from auth_utils import require_auth, get_current_user
from sqlalchemy import desc
from datetime import datetime

bp = Blueprint('checkin', __name__)

VALID_RESPONSES = ('ok', 'not_ok')
VALID_CHANNELS  = ('app', 'whatsapp', 'sms')


def _serialize(c, mother_name: str | None = None):
    return {
        "id":          c.id,
        "mother_id":   c.mother_id,
        "mother_name": mother_name or (c.mother.mother_name if c.mother else None),
        "response":    c.response,
        "comment":     c.comment,
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

    checkin = DailyCheckin(
        mother_id=mother_id,
        response=response,
        comment=data.get('comment', '').strip() or None,
        channel=channel,
        created_at=datetime.utcnow(),
    )
    db.session.add(checkin)
    db.session.commit()

    return jsonify({
        "message": "Check-in recorded.",
        **_serialize(checkin, mother.mother_name),
    }), 201


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
    """
    limit = min(int(request.args.get('limit', 50)), 200)

    # Get all active mother IDs assigned to this CHW
    assignments = (MotherCHWAssignment.query
                   .filter_by(chw_id=chw_id, status='active')
                   .all())
    mother_ids = [a.mother_id for a in assignments]

    if not mother_ids:
        return jsonify({"checkins": [], "total": 0}), 200

    checkins = (DailyCheckin.query
                .filter(DailyCheckin.mother_id.in_(mother_ids))
                .order_by(desc(DailyCheckin.created_at))
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
