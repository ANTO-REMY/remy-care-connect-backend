"""
socket_manager.py
─────────────────
Single Flask-SocketIO instance shared across all blueprints.
Import `socketio` from here wherever you need to emit events
(avoids circular imports with app.py / blueprints).
"""

from flask_socketio import SocketIO

socketio = SocketIO(
    cors_allowed_origins=[
        "http://localhost:8080",
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    async_mode="eventlet",
    # Allow the JWT token to be passed as a query-string param on connect
    # e.g. ?token=<JWT>
    logger=False,
    engineio_logger=False,
)
