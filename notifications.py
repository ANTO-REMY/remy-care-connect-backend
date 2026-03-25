"""notifications.py
────────────────
Firebase Cloud Messaging (FCM) push-notification helpers.

Initialises firebase_admin once at startup and exposes send_push() to
deliver notifications to all device tokens registered for a user.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

# ── Firebase admin globals ────────────────────────────────────────────────────
firebase_admin = None  # type: ignore[assignment]
messaging = None  # type: ignore[assignment]
_firebase_initialised = False


def _log_push_attempt(
    *,
    user_id: int,
    event: str,
    title: str,
    body: str,
    token_count: int,
    success_count: int,
    failure_count: int,
    stale_token_count: int,
    status: str,
    error: Optional[str] = None,
) -> None:
    """Best-effort insert to telemetry table. Never raises."""
    from app import db

    try:
        db.session.execute(
            db.text(
                """
                INSERT INTO push_notification_logs
                  (user_id, event, title, body, token_count, success_count, failure_count, stale_token_count, status, error)
                VALUES
                  (:user_id, :event, :title, :body, :token_count, :success_count, :failure_count, :stale_token_count, :status, :error)
                """
            ),
            {
                "user_id": user_id,
                "event": event,
                "title": title,
                "body": body,
                "token_count": token_count,
                "success_count": success_count,
                "failure_count": failure_count,
                "stale_token_count": stale_token_count,
                "status": status,
                "error": error,
            },
        )
        db.session.commit()
    except Exception as exc:  # pragma: no cover
        db.session.rollback()
        log.debug(f"[FCM] Could not write push telemetry log: {exc}")


def create_user_notification(
    *,
    user_id: int,
    event_type: str,
    title: str,
    message: str,
    url: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    emit_socket_event: bool = True,
) -> Optional[dict]:
    """Persist an in-app notification and optionally emit it over socket."""
    from app import db

    now = datetime.now(timezone.utc)
    try:
        row = db.session.execute(
            db.text(
                """
                INSERT INTO user_notifications
                  (user_id, event_type, title, message, url, entity_type, entity_id, is_read, created_at)
                VALUES
                  (:user_id, :event_type, :title, :message, :url, :entity_type, :entity_id, false, :created_at)
                RETURNING id
                """
            ),
            {
                "user_id": user_id,
                "event_type": event_type,
                "title": title,
                "message": message,
                "url": url,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "created_at": now,
            },
        ).first()
        db.session.commit()

        notif = {
            "id": row[0] if row else None,
            "user_id": user_id,
            "event_type": event_type,
            "title": title,
            "message": message,
            "url": url,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "is_read": False,
            "created_at": now.isoformat(),
        }

        if emit_socket_event:
            from socket_manager import socketio
            socketio.emit("notification:new", notif, to=f"user:{user_id}")

        return notif
    except Exception as exc:  # pragma: no cover
        db.session.rollback()
        log.debug(f"[FCM] Could not create user notification: {exc}")
        return None


def _is_stale_token_error(exc: Exception) -> bool:
    """Best-effort detection for invalid/unregistered FCM tokens."""
    text = str(exc).lower()
    return any(marker in text for marker in (
        'registration-token-not-registered',
        'requested entity was not found',
        'unregistered',
        'invalid registration token',
        'invalidargument',
    ))


def init_firebase() -> None:
    """Call once at app startup after GOOGLE_APPLICATION_CREDENTIALS is set."""
    global _firebase_initialised, firebase_admin, messaging
    if _firebase_initialised:
        return

    try:
        from firebase_admin import credentials, initialize_app, messaging as _messaging  # type: ignore[import]

        cred = credentials.ApplicationDefault()
        firebase_admin = initialize_app(cred)
        messaging = _messaging
        _firebase_initialised = True
        log.info("[FCM] Firebase initialised for push notifications.")
    except Exception as exc:  # pragma: no cover - defensive logging
        log.warning(f"[FCM] Failed to initialise Firebase: {exc}")


def send_push(user_id: int, title: str, body: str, data: Optional[dict] = None) -> bool:
    """Send a push notification to all devices registered for `user_id`."""
    # Imported lazily to avoid circular imports (models.py imports db from app.py).
    from app import db

    event = (data or {}).get("event", "unknown")

    if not _firebase_initialised or messaging is None:
        log.debug(f"[FCM] Skipped push for user {user_id} — Firebase not initialised.")
        _log_push_attempt(
            user_id=user_id,
            event=event,
            title=title,
            body=body,
            token_count=0,
            success_count=0,
            failure_count=0,
            stale_token_count=0,
            status="skipped",
            error="firebase_not_initialised",
        )
        return False

    # Fetch all FCM tokens for this user
    result = db.session.execute(
        db.text("SELECT fcm_token FROM device_tokens WHERE user_id = :uid"),
        {"uid": user_id},
    )
    tokens = [row[0] for row in result.fetchall()]

    if not tokens:
        log.debug(f"[FCM] No device tokens found for user {user_id}")
        _log_push_attempt(
            user_id=user_id,
            event=event,
            title=title,
            body=body,
            token_count=0,
            success_count=0,
            failure_count=0,
            stale_token_count=0,
            status="skipped",
            error="no_device_tokens",
        )
        return False

    try:
        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
            tokens=tokens,
        )
        response = messaging.send_each_for_multicast(message)
        log.info(
            f"[FCM] Sent {response.success_count}/{len(tokens)} notifications to user {user_id}",
        )

        # Cleanup stale tokens so future sends are healthier.
        stale_tokens = []
        for token, send_resp in zip(tokens, response.responses):
            if send_resp.success:
                continue
            if send_resp.exception and _is_stale_token_error(send_resp.exception):
                stale_tokens.append(token)

        if stale_tokens:
            for stale_token in stale_tokens:
                db.session.execute(
                    db.text("DELETE FROM device_tokens WHERE user_id = :uid AND fcm_token = :token"),
                    {"uid": user_id, "token": stale_token},
                )
            db.session.commit()
            log.info(f"[FCM] Removed {len(stale_tokens)} stale token(s) for user {user_id}")

        if response.success_count == len(tokens):
            status = "success"
        elif response.success_count > 0:
            status = "partial"
        else:
            status = "failed"

        _log_push_attempt(
            user_id=user_id,
            event=event,
            title=title,
            body=body,
            token_count=len(tokens),
            success_count=response.success_count,
            failure_count=len(tokens) - response.success_count,
            stale_token_count=len(stale_tokens),
            status=status,
        )

        return response.success_count > 0
    except Exception as exc:  # pragma: no cover - defensive logging
        log.warning(f"[FCM] Failed to send push to user {user_id}: {exc}")
        _log_push_attempt(
            user_id=user_id,
            event=event,
            title=title,
            body=body,
            token_count=len(tokens),
            success_count=0,
            failure_count=len(tokens),
            stale_token_count=0,
            status="failed",
            error=str(exc),
        )
        return False
