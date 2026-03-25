"""
routes_notifications.py
───────────────────────
Read in-app notifications and push delivery telemetry for the current user.
"""

from datetime import datetime, timezone, timedelta
from flask import Blueprint, jsonify, request
from auth_utils import require_auth, get_current_user
from models import db, PushNotificationLog, UserNotification

bp = Blueprint('notifications', __name__)


def _serialize_user_notification(n: UserNotification) -> dict:
    return {
        "id": n.id,
        "event_type": n.event_type,
        "title": n.title,
        "message": n.message,
        "url": n.url,
        "entity_type": n.entity_type,
        "entity_id": n.entity_id,
        "is_read": bool(n.is_read),
        "read_at": n.read_at.isoformat() if n.read_at else None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


@bp.route('/notifications', methods=['GET'])
@require_auth
def list_notifications():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Authentication required."}), 401

    limit = request.args.get('limit', default=20, type=int)
    limit = max(1, min(limit, 100))
    unread_only = str(request.args.get('unread_only', 'false')).lower() in ('1', 'true', 'yes')

    q = UserNotification.query.filter(UserNotification.user_id == user.id)
    if unread_only:
        q = q.filter(UserNotification.is_read.is_(False))

    notifications = q.order_by(UserNotification.created_at.desc()).limit(limit).all()
    unread_count = UserNotification.query.filter(
        UserNotification.user_id == user.id,
        UserNotification.is_read.is_(False),
    ).count()

    return jsonify({
        "notifications": [_serialize_user_notification(n) for n in notifications],
        "unread_count": unread_count,
        "total": len(notifications),
    }), 200


@bp.route('/notifications/unread-count', methods=['GET'])
@require_auth
def get_unread_count():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Authentication required."}), 401

    unread_count = UserNotification.query.filter(
        UserNotification.user_id == user.id,
        UserNotification.is_read.is_(False),
    ).count()
    return jsonify({"unread_count": unread_count}), 200


@bp.route('/notifications/<int:notification_id>/read', methods=['PATCH'])
@require_auth
def mark_notification_read(notification_id: int):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Authentication required."}), 401

    n = UserNotification.query.filter_by(id=notification_id, user_id=user.id).first()
    if not n:
        return jsonify({"error": "Notification not found."}), 404

    if not n.is_read:
        n.is_read = True
        n.read_at = datetime.now(timezone.utc)
        db.session.commit()

    unread_count = UserNotification.query.filter(
        UserNotification.user_id == user.id,
        UserNotification.is_read.is_(False),
    ).count()
    return jsonify({"message": "Notification marked as read.", "unread_count": unread_count}), 200


@bp.route('/notifications/read-all', methods=['PATCH'])
@require_auth
def mark_all_notifications_read():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Authentication required."}), 401

    now = datetime.now(timezone.utc)
    db.session.query(UserNotification).filter(
        UserNotification.user_id == user.id,
        UserNotification.is_read.is_(False),
    ).update({"is_read": True, "read_at": now}, synchronize_session=False)
    db.session.commit()

    return jsonify({"message": "All notifications marked as read.", "unread_count": 0}), 200


@bp.route('/notifications/metrics', methods=['GET'])
@require_auth
def get_notification_metrics():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Authentication required."}), 401

    days = request.args.get('days', default=7, type=int)
    days = max(1, min(days, 30))
    limit = request.args.get('limit', default=25, type=int)
    limit = max(1, min(limit, 100))

    since = datetime.now(timezone.utc) - timedelta(days=days)

    logs = (
        PushNotificationLog.query
        .filter(PushNotificationLog.user_id == user.id)
        .filter(PushNotificationLog.created_at >= since)
        .order_by(PushNotificationLog.created_at.desc())
        .all()
    )

    totals = {
        "attempts": len(logs),
        "token_count": sum(l.token_count for l in logs),
        "success_count": sum(l.success_count for l in logs),
        "failure_count": sum(l.failure_count for l in logs),
        "stale_token_count": sum(l.stale_token_count for l in logs),
    }

    by_status = {"success": 0, "partial": 0, "failed": 0, "skipped": 0}
    by_event = {}

    for log in logs:
        by_status[log.status] = by_status.get(log.status, 0) + 1
        by_event[log.event] = by_event.get(log.event, 0) + 1

    recent = [
        {
            "id": l.id,
            "event": l.event,
            "title": l.title,
            "status": l.status,
            "token_count": l.token_count,
            "success_count": l.success_count,
            "failure_count": l.failure_count,
            "stale_token_count": l.stale_token_count,
            "error": l.error,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs[:limit]
    ]

    return jsonify({
        "window_days": days,
        "totals": totals,
        "by_status": by_status,
        "by_event": by_event,
        "recent": recent,
    }), 200
