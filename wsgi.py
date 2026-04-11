from app import create_app
from socket_manager import socketio

app = create_app()

if __name__ == '__main__':
    # Use socketio.run() so Socket.IO is served alongside HTTP.
    # allow_unsafe_werkzeug suppresses the Flask 3.x debug-mode warning.
    # use_reloader=False prevents the gevent/threading double-bind on Windows.
    print("[wsgi] Starting Remy Care Connect backend on http://0.0.0.0:5001 ...")
    socketio.run(
        app,
        host='0.0.0.0',
        port=5001,
        debug=True,
        use_reloader=False,
        allow_unsafe_werkzeug=True,
    )
