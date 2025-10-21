from functools import wraps
from flask import request, jsonify, session, current_app
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, create_access_token, create_refresh_token
from models import User, UserSession, db
import hashlib
import random
import string
from datetime import datetime, timedelta
import secrets

def generate_otp():
    """Generate a 5-digit OTP code"""
    return ''.join(random.choices(string.digits, k=5))

def hash_pin(pin):
    """Hash a PIN using SHA256"""
    return hashlib.sha256(pin.encode()).hexdigest()

def verify_pin(pin, pin_hash):
    """Verify a PIN against its hash"""
    return hashlib.sha256(pin.encode()).hexdigest() == pin_hash

def create_session_token():
    """Generate a secure session token"""
    return secrets.token_urlsafe(32)

def create_user_session(user_id, device_info=None, ip_address=None):
    """Create a new user session in database"""
    session_token = create_session_token()
    expires_at = datetime.utcnow() + timedelta(hours=24)
    
    user_session = UserSession(
        user_id=user_id,
        session_token=session_token,
        device_info=device_info,
        ip_address=ip_address,
        created_at=datetime.utcnow(),
        expires_at=expires_at,
        last_activity=datetime.utcnow()
    )
    
    db.session.add(user_session)
    db.session.commit()
    
    return session_token

def validate_session_token(session_token):
    """Validate a session token and return user if valid"""
    user_session = UserSession.query.filter_by(
        session_token=session_token,
        is_active=True
    ).first()
    
    if not user_session:
        return None
    
    # Check if session is expired
    if user_session.expires_at < datetime.utcnow():
        user_session.is_active = False
        db.session.commit()
        return None
    
    # Update last activity
    user_session.last_activity = datetime.utcnow()
    db.session.commit()
    
    return user_session.user

def require_auth(f):
    """Decorator for hybrid authentication - supports both JWT and session"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = None
        auth_method = None
        
        # Try JWT authentication first
        try:
            verify_jwt_in_request()
            user_id = get_jwt_identity()
            user = User.query.get(user_id)
            auth_method = 'jwt'
        except:
            # Try session authentication
            session_token = session.get('session_token')
            if session_token:
                user = validate_session_token(session_token)
                auth_method = 'session'
        
        if not user or not user.is_active or not user.is_verified:
            return jsonify({'error': 'Authentication required'}), 401
        
        # Add user and auth method to request context
        request.current_user = user
        request.auth_method = auth_method
        
        return f(*args, **kwargs)
    
    return decorated_function

def require_role(*allowed_roles):
    """Decorator to require specific user roles"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not hasattr(request, 'current_user'):
                return jsonify({'error': 'Authentication required'}), 401
            
            if request.current_user.role not in allowed_roles:
                return jsonify({'error': 'Insufficient permissions'}), 403
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator

def get_current_user():
    """Get the current authenticated user"""
    return getattr(request, 'current_user', None)

def logout_user_sessions(user_id, current_session_token=None):
    """Logout all user sessions except current one (optional)"""
    query = UserSession.query.filter_by(user_id=user_id, is_active=True)
    
    if current_session_token:
        query = query.filter(UserSession.session_token != current_session_token)
    
    sessions = query.all()
    for session_obj in sessions:
        session_obj.is_active = False
    
    db.session.commit()
    return len(sessions)
