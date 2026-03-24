"""
socket_manager.py
─────────────────
Single Flask-SocketIO instance shared across all blueprints.
Import `socketio` from here wherever you need to emit events
(avoids circular imports with app.py / blueprints).
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
    message_queue=redis_url,  # Redis message broker for multi-worker deployments
    async_mode="gevent",  # Use gevent for production (more efficient than threading)
    # Allow the JWT token to be passed as a query-string param on connect
    # e.g. ?token=<JWT>
    logger=False,
    engineio_logger=False,
)
