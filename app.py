from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from dotenv import load_dotenv
import os

# Load environment variables from .env if present
load_dotenv()

from socket_manager import socketio

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()

def create_app():
    app = Flask(__name__)
    
    # Database configuration
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/remyafya')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['DEBUG'] = True
    
    # JWT configuration
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'remy-care-connect-jwt-secret-key-change-in-production')
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = 86400  # 24 hours in seconds
    app.config['JWT_REFRESH_TOKEN_EXPIRES'] = 2592000  # 30 days in seconds
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'remy-care-connect-secret-key-change-in-production')
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    # CORS: origins read from CORS_ORIGINS env var (comma-separated).
    # In production set: CORS_ORIGINS=https://your-app.vercel.app
    # Falls back to local dev origins if the variable is not set.
    _cors_origins_raw = os.getenv(
        'CORS_ORIGINS',
        'http://localhost:5173,http://localhost:8080,http://localhost:3000'
    )
    _cors_origins = [o.strip() for o in _cors_origins_raw.split(',') if o.strip()]
    CORS(app, origins=_cors_origins, supports_credentials=True)
    socketio.init_app(app)

    from routes.routes_health import bp as health_bp
    from auth import bp as auth_bp
    from routes.routes_mothers import bp as mothers_bp
    from routes.routes_verifications import bp as verifications_bp
    from routes.routes_chws import bp as chws_bp
    from routes.routes_nurses import bp as nurses_bp
    from routes.routes_materials import bp as materials_bp
    from routes.routes_assignment import bp as assignment_bp
    from routes.routes_escalations import bp as escalations_bp
    from routes.routes_appointments import bp as appointments_bp
    from routes.routes_nextofkin import bp as nextofkin_bp
    from routes.routes_notifications import bp as notifications_bp
    from routes.routes_photos import bp as photos_bp
    from routes.routes_locations import bp as locations_bp
    from routes.routes_resources import bp as resources_bp
    app.register_blueprint(health_bp, url_prefix='/api/v1')
    app.register_blueprint(auth_bp, url_prefix='/api/v1')
    app.register_blueprint(mothers_bp, url_prefix='/api/v1')
    app.register_blueprint(verifications_bp, url_prefix='/api/v1')
    app.register_blueprint(chws_bp, url_prefix='/api/v1')
    app.register_blueprint(nurses_bp, url_prefix='/api/v1')
    app.register_blueprint(materials_bp, url_prefix='/api/v1')
    app.register_blueprint(assignment_bp, url_prefix='/api/v1')
    app.register_blueprint(escalations_bp, url_prefix='/api/v1')
    app.register_blueprint(appointments_bp, url_prefix='/api/v1')
    app.register_blueprint(nextofkin_bp, url_prefix='/api/v1')
    app.register_blueprint(notifications_bp, url_prefix='/api/v1')
    app.register_blueprint(photos_bp, url_prefix='/api/v1')
    app.register_blueprint(locations_bp, url_prefix='/api/v1')
    app.register_blueprint(resources_bp, url_prefix='/api/v1')
    from routes.routes_checkin import bp as checkin_bp
    app.register_blueprint(checkin_bp, url_prefix='/api/v1')
    from routes.routes_device_tokens import bp as device_tokens_bp
    app.register_blueprint(device_tokens_bp, url_prefix='/api/v1')

    # Register Socket.IO event handlers (import for side-effects)
    import routes.socket_events  # noqa: F401

    # Initialise Firebase Cloud Messaging (no-op if credentials not configured)
    # Imported lazily to avoid circular imports during app startup.
    from notifications import init_firebase
    init_firebase()

    return app
