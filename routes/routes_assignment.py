from flask import Blueprint, jsonify, request
from models import db, CHW, Mother, User
from models_standard import MotherCHWAssignment

bp = Blueprint('assignment', __name__)

@bp.route('/chws/<int:chw_id>/mothers', methods=['GET'])
def get_assigned_mothers(chw_id):
    assignments = MotherCHWAssignment.query.filter_by(chw_id=chw_id).all()
    result = []
    for assignment in assignments:
        mother = Mother.query.get(assignment.mother_id)
        user = User.query.get(mother.user_id)
        result.append({
            "mother_id": mother.id,
            "name": mother.mother_name,
            "phone": user.phone_number,
            "location": mother.location
        })
    return jsonify({"mothers": result}), 200

@bp.route('/chws/<int:chw_id>/assign_mother', methods=['POST'])
def assign_mother_to_chw(chw_id):
    data = request.get_json()
    mother_id = data.get('mother_id')
    if not mother_id:
        return jsonify({"error": "mother_id is required."}), 400

    # Validate CHW profile exists (not just the user)
    chw = CHW.query.get(chw_id)
    if not chw:
        # Help diagnose: check if a user with this id exists but has no CHW profile
        user = User.query.get(chw_id)
        if user and user.role == 'chw':
            return jsonify({
                "error": f"CHW profile not found for user {chw_id}. "
                         "The CHW registered but their profile was not created. "
                         "Please contact support or re-register."
            }), 404
        return jsonify({"error": f"CHW with id {chw_id} not found."}), 404

    # Validate Mother profile exists
    mother = Mother.query.get(mother_id)
    if not mother:
        return jsonify({"error": f"Mother with id {mother_id} not found."}), 404

    # Enforce max 2 mothers per CHW
    existing_assignments = MotherCHWAssignment.query.filter_by(chw_id=chw_id).count()
    if existing_assignments >= 2:
        return jsonify({"error": "CHW already has 2 mothers assigned."}), 400

    # Prevent duplicate assignment
    if MotherCHWAssignment.query.filter_by(chw_id=chw_id, mother_id=mother_id).first():
        return jsonify({"error": "Mother already assigned to this CHW."}), 400

    try:
        assignment = MotherCHWAssignment(
            chw_id=chw_id,
            mother_id=mother_id,
            chw_name=chw.chw_name,
            mother_name=mother.mother_name,
            status='active'
        )
        db.session.add(assignment)
        db.session.commit()
        return jsonify({
            "message": "Mother assigned to CHW successfully.",
            "chw_name": chw.chw_name,
            "mother_name": mother.mother_name,
            "status": "active",
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Assignment failed: {str(e)}"}), 500
