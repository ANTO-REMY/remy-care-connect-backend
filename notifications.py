"""notifications.py
────────────────
Firebase Cloud Messaging (FCM) push-notification helpers.

Initialises firebase_admin once at startup and exposes send_push() to
deliver notifications to all device tokens registered for a user.
"""

import logging
from typing import Optional

log = logging.getLogger(__name__)

# ── Firebase admin globals ────────────────────────────────────────────────────
firebase_admin = None  # type: ignore[assignment]
messaging = None  # type: ignore[assignment]
_firebase_initialised = False


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

    if not _firebase_initialised or messaging is None:
        log.debug(f"[FCM] Skipped push for user {user_id} — Firebase not initialised.")
        return False

    # Fetch all FCM tokens for this user
    result = db.session.execute(
        db.text("SELECT fcm_token FROM device_tokens WHERE user_id = :uid"),
        {"uid": user_id},
    )
    tokens = [row[0] for row in result.fetchall()]

    if not tokens:
        log.debug(f"[FCM] No device tokens found for user {user_id}")
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
        return response.success_count > 0
    except Exception as exc:  # pragma: no cover - defensive logging
        log.warning(f"[FCM] Failed to send push to user {user_id}: {exc}")
        return False
