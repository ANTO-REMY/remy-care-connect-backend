"""
routes_locations.py — Nairobi administrative location endpoints.

Public read endpoints (no auth required):
    GET /locations/sub-counties
    GET /locations/sub-counties/<id>/wards

Authenticated write endpoint:
    PATCH /locations/ward   → saves ward_id to the caller's role profile
"""

from flask import Blueprint, request, jsonify
from models import db, SubCounty, Ward, Mother, CHW, Nurse
from auth_utils import require_auth, get_current_user

bp = Blueprint('locations', __name__)


# ── Read endpoints ────────────────────────────────────────────────────────────

@bp.route('/locations/sub-counties', methods=['GET'])
def get_sub_counties():
    """Return all Nairobi sub-counties, ordered alphabetically."""
    sub_counties = SubCounty.query.order_by(SubCounty.name).all()
    return jsonify([
        {'id': sc.id, 'name': sc.name}
        for sc in sub_counties
    ]), 200


@bp.route('/locations/sub-counties/<int:sub_county_id>/wards', methods=['GET'])
def get_wards(sub_county_id):
    """Return all wards for a given sub-county, ordered alphabetically."""
    sub_county = SubCounty.query.get(sub_county_id)
    if not sub_county:
        return jsonify({'error': 'Sub-county not found.'}), 404

    wards = (
        Ward.query
        .filter_by(sub_county_id=sub_county_id)
        .order_by(Ward.name)
        .all()
    )
    return jsonify([
        {'id': w.id, 'name': w.name, 'sub_county_id': w.sub_county_id}
        for w in wards
    ]), 200


# ── Write endpoint ────────────────────────────────────────────────────────────

@bp.route('/locations/ward', methods=['PATCH'])
@require_auth
def save_ward():
    """
    Save the chosen ward_id to the calling user's role-specific profile row.
    Body: { "ward_id": <int> }
    The user's role is determined from the JWT payload.
    """
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Authentication required.'}), 401

    data = request.get_json() or {}

    ward_id = data.get('ward_id')
    if not ward_id:
        return jsonify({'error': 'ward_id is required.'}), 400

    # Validate the ward exists
    ward = Ward.query.get(ward_id)
    if not ward:
        return jsonify({'error': 'Ward not found.'}), 404

    try:
        if user.role == 'mother':
            profile = Mother.query.filter_by(user_id=user.id).first()
            if not profile:
                return jsonify({'error': 'Mother profile not found.'}), 404
            profile.ward_id = ward_id

        elif user.role == 'chw':
            profile = CHW.query.filter_by(user_id=user.id).first()
            if not profile:
                return jsonify({'error': 'CHW profile not found.'}), 404
            profile.ward_id = ward_id

        elif user.role == 'nurse':
            profile = Nurse.query.filter_by(user_id=user.id).first()
            if not profile:
                return jsonify({'error': 'Nurse profile not found.'}), 404
            profile.ward_id = ward_id

        else:
            return jsonify({'error': 'Unsupported role.'}), 400

        db.session.commit()
        return jsonify({
            'message': 'Ward saved successfully.',
            'ward_id': ward_id,
            'ward_name': ward.name,
            'sub_county_id': ward.sub_county_id
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
