"""
routes_device_tokens.py
───────────────────────
CRUD for FCM device token registration.

Endpoints:
  POST   /device-tokens         — register / update a device token
  DELETE /device-tokens          — remove a device token (on logout)
"""

from flask import Blueprint, jsonify, request
from models import db
from auth_utils import require_auth, get_current_user
from datetime import datetime, timezone

bp = Blueprint('device_tokens', __name__)


@bp.route('/device-tokens', methods=['POST'])
@require_auth
def register_device_token():
    """
    Register an FCM device token for the current user.
    Body: { "fcm_token": "...", "device_info": "..." (optional) }
    Upserts — if the token already exists for this user, updates timestamp.
    """
    user = get_current_user()
    data = request.get_json() or {}
    fcm_token = data.get('fcm_token', '').strip()

    if not fcm_token:
        return jsonify({"error": "fcm_token is required."}), 400

    device_info = data.get('device_info', '')

    now = datetime.now(timezone.utc)
    # Upsert via raw SQL (SQLAlchemy model not yet defined for device_tokens)
    db.session.execute(
        db.text("""
            INSERT INTO device_tokens (user_id, fcm_token, device_info, created_at, updated_at)
            VALUES (:uid, :token, :info, :now, :now)
            ON CONFLICT (user_id, fcm_token) DO UPDATE
            SET device_info = :info, updated_at = :now
        """),
        {"uid": user.id, "token": fcm_token, "info": device_info, "now": now},
    )
    db.session.commit()

    return jsonify({"message": "Device token registered."}), 201


@bp.route('/device-tokens', methods=['DELETE'])
@require_auth
def remove_device_token():
    """
    Remove an FCM device token (call on logout).
    Body: { "fcm_token": "..." }
    """
    user = get_current_user()
    data = request.get_json() or {}
    fcm_token = data.get('fcm_token', '').strip()

    if not fcm_token:
        return jsonify({"error": "fcm_token is required."}), 400

    db.session.execute(
        db.text("DELETE FROM device_tokens WHERE user_id = :uid AND fcm_token = :token"),
        {"uid": user.id, "token": fcm_token},
    )
    db.session.commit()

    return jsonify({"message": "Device token removed."}), 200
