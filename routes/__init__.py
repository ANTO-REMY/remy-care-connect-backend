# Routes package initialization
# This file makes the routes directory a Python package

from .routes_health import bp as health_bp
from .routes_mothers import bp as mothers_bp
from .routes_verifications import bp as verifications_bp
from .routes_chws import bp as chws_bp
from .routes_nurses import bp as nurses_bp
from .routes_materials import bp as materials_bp
from .routes_assignment import bp as assignment_bp
from .routes_nextofkin import bp as nextofkin_bp

__all__ = [
    'health_bp',
    'mothers_bp', 
    'verifications_bp',
    'chws_bp',
    'nurses_bp',
    'materials_bp',
    'assignment_bp',
    'nextofkin_bp'
]
