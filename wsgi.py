from app import create_app
from socket_manager import socketio

app = create_app()

if __name__ == '__main__':
    # Use socketio.run() so Socket.IO is served alongside HTTP
    socketio.run(app, host='0.0.0.0', port=5001, debug=True, use_reloader=False)
