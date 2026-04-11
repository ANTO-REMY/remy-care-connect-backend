"""
routes_resources.py
===================
CRUD for Resource records.

Endpoints:
  GET    /resources            – list (filterable by role)
"""

from flask import Blueprint, jsonify, request
from models import db, Resource
from auth_utils import require_auth, get_current_user

bp = Blueprint('resources', __name__)

# ── Serialiser ────────────────────────────────────────────────────────────────

def _serialize_resource(resource):
    """Manual serialization for Resource objects"""
    return {
        "id": resource.id,
        "title": resource.title,
        "description": resource.description,
        "category": resource.category,
        "target_role": resource.target_role,
        "content_type": resource.content_type,
        "url": resource.url,
        "thumbnail": resource.thumbnail,
        "created_at": resource.created_at.isoformat() if resource.created_at else None,
    }

# ── List resources ────────────────────────────────────────────────────────────

@bp.route('/resources', methods=['GET'])
@require_auth
def list_resources():
    """
    Filter by: ?role=mother|chw|nurse
    Returns all resources or filtered by target_role.
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({"error": "Unauthorized."}), 401

    try:
        # Start with base query
        q = Resource.query

        # Apply role filter if provided
        role = request.args.get('role')
        if role:
            # Validate role parameter
            valid_roles = ['mother', 'chw', 'nurse']
            if role not in valid_roles:
                return jsonify({
                    "error": f"Invalid role parameter. Must be one of: {', '.join(valid_roles)}"
                }), 400
            
            q = q.filter_by(target_role=role)

        # Order by creation date (newest first)
        resources = q.order_by(Resource.created_at.desc()).all()
        
        return jsonify({
            "data": [_serialize_resource(r) for r in resources],
            "count": len(resources)
        }), 200

    except Exception as e:
        return jsonify({"error": f"Failed to retrieve resources: {str(e)}"}), 500