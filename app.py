from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_session import Session
from dotenv import load_dotenv
import os
import redis

# Load environment variables from .env if present
load_dotenv()

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
sess = Session()

def create_app():
    app = Flask(__name__)
    
    # Database configuration
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql+psycopg://postgres:postgres@localhost:5432/remyafya')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['DEBUG'] = True
    
    # JWT configuration
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'remy-care-connect-jwt-secret-key-change-in-production')
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = 86400  # 24 hours in seconds
    app.config['JWT_REFRESH_TOKEN_EXPIRES'] = 2592000  # 30 days in seconds
    
    # Session configuration for hybrid auth
    app.config['SESSION_TYPE'] = 'redis'
    app.config['SESSION_REDIS'] = redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379'))
    app.config['SESSION_PERMANENT'] = False
    app.config['SESSION_USE_SIGNER'] = True
    app.config['SESSION_KEY_PREFIX'] = 'remy_care:'
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'remy-care-connect-secret-key-change-in-production')
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    sess.init_app(app)

    from routes.routes_health import bp as health_bp
    from auth import bp as auth_bp
    from routes.routes_mothers import bp as mothers_bp
    from routes.routes_verifications import bp as verifications_bp
    from routes.routes_chws import bp as chws_bp
    from routes.routes_nurses import bp as nurses_bp
    from routes.routes_materials import bp as materials_bp
    from routes.routes_assignment import bp as assignment_bp
    from routes.routes_nextofkin import bp as nextofkin_bp
    app.register_blueprint(health_bp, url_prefix='/api/v1')
    app.register_blueprint(auth_bp, url_prefix='/api/v1')
    app.register_blueprint(mothers_bp, url_prefix='/api/v1')
    app.register_blueprint(verifications_bp, url_prefix='/api/v1')
    app.register_blueprint(chws_bp, url_prefix='/api/v1')
    app.register_blueprint(nurses_bp, url_prefix='/api/v1')
    app.register_blueprint(materials_bp, url_prefix='/api/v1')
    app.register_blueprint(assignment_bp, url_prefix='/api/v1')
    app.register_blueprint(nextofkin_bp, url_prefix='/api/v1')

    return app
