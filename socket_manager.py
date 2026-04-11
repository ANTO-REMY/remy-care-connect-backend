"""
socket_manager.py
─────────────────
Single Flask-SocketIO instance shared across all blueprints.
Import `socketio` from here wherever you need to emit events
(avoids circular imports with app.py / blueprints).

NOTE: async_mode is set to "threading" for Python 3.13 compatibility.
gevent is unstable on Python 3.13 and causes WinError 10048 (port not released)
when the server shuts down unexpectedly on Windows.
"""

import os
from flask_socketio import SocketIO

# Get Redis URL from environment; default to local development
redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')

socketio = SocketIO(
    cors_allowed_origins=[
        "http://localhost:8080",
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    # message_queue=redis_url,  # Disabled for local Windows development without Docker
    # Python 3.13-safe websocket runtime — threading is stable; gevent is not on Py3.13/Windows.
    async_mode="threading",
    # Avoid handshake-level hard failures when auth rejects; app code disconnects unauthorized clients.
    always_connect=True,
    # Allow the JWT token to be passed as a query-string param on connect
    # e.g. ?token=<JWT>
    logger=False,
    engineio_logger=False,
)
