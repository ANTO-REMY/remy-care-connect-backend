"""
notifications.py
────────────────
Firebase Cloud Messaging (FCM) push-notification helpers.

This is a **placeholder** — actual FCM integration requires:
  1. A Firebase service-account JSON key (GOOGLE_APPLICATION_CREDENTIALS)
  2. `pip install firebase-admin`
  3. Initialising `firebase_admin.initialize_app()` once at startup

Once configured, call `send_push(user_id, title, body, data)` from any
route handler to push a notification to all devices registered for that user.
"""

import logging

log = logging.getLogger(__name__)

# ── Placeholder flag ──────────────────────────────────────────────────────────
# Set to True once firebase_admin is configured in app.py
_firebase_initialised = False


def init_firebase():
    """
    Call once at app startup after setting GOOGLE_APPLICATION_CREDENTIALS.

    Example (in app.py):
        from notifications import init_firebase
        init_firebase()
    """
    global _firebase_initialised
    try:
        # import firebase_admin
        # from firebase_admin import credentials
        # cred = credentials.ApplicationDefault()
        # firebase_admin.initialize_app(cred)
        # _firebase_initialised = True
        log.info("[FCM] Firebase not yet configured — push notifications disabled.")
    except Exception as e:
        log.warning(f"[FCM] Failed to initialise Firebase: {e}")


def send_push(user_id: int, title: str, body: str, data: dict | None = None) -> bool:
    """
    Send a push notification to all devices registered for `user_id`.

    Returns True if at least one message was sent successfully.
    Returns False (and logs) when Firebase is not configured.

    Parameters
    ----------
    user_id : int
        The users.id to target.
    title : str
        Notification title visible in the system tray.
    body : str
        Notification body text.
    data : dict, optional
        Arbitrary key-value payload delivered silently to the app.
    """
    if not _firebase_initialised:
        log.debug(f"[FCM] Skipped push for user {user_id} — Firebase not initialised.")
        return False

    # TODO: Query device_tokens table for user_id, build FCM messages, send.
    # from firebase_admin import messaging
    # from models import db
    # tokens = db.session.execute(
    #     "SELECT fcm_token FROM device_tokens WHERE user_id = :uid",
    #     {"uid": user_id},
    # ).scalars().all()
    #
    # if not tokens:
    #     return False
    #
    # message = messaging.MulticastMessage(
    #     notification=messaging.Notification(title=title, body=body),
    #     data=data or {},
    #     tokens=tokens,
    # )
    # response = messaging.send_each_for_multicast(message)
    # log.info(f"[FCM] Sent {response.success_count}/{len(tokens)} to user {user_id}")
    # return response.success_count > 0

    return False
