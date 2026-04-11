from flask import Blueprint, jsonify, request
from models import db, CHW, Mother, Nurse, User
from models_standard import MotherCHWAssignment
from auth_utils import require_auth, require_role, get_current_user
from datetime import datetime

bp = Blueprint('assignment', __name__)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _serialize_assignment(a):
    return {
        "id": a.id,
        "mother_id": a.mother_id,
        "mother_name": a.mother_name,
        "chw_id": a.chw_id,
        "chw_name": a.chw_name,
        "assigned_at": a.assigned_at.isoformat() if a.assigned_at else None,
        "status": a.status,
    }

# ── CHW endpoints ─────────────────────────────────────────────────────────────

@bp.route('/chws/<int:chw_id>/mothers', methods=['GET'])
def get_assigned_mothers(chw_id):
    """Return all mothers assigned to a CHW.  Optional ?status=active|inactive"""
    status_filter = request.args.get('status')
    q = MotherCHWAssignment.query.filter_by(chw_id=chw_id)
    if status_filter:
        q = q.filter_by(status=status_filter)
    assignments = q.all()
    result = []
    for a in assignments:
        mother = Mother.query.get(a.mother_id)
        if not mother:
            continue
        user = User.query.get(mother.user_id)
        result.append({
            "assignment_id": a.id,
            "mother_id": mother.id,
            "user_id": mother.user_id,        # users.id — needed for appointment creation
            "name": mother.mother_name,
            "phone": user.phone_number if user else None,
            "location": mother.location,
            "status": a.status,
            "assigned_at": a.assigned_at.isoformat() if a.assigned_at else None,
        })
    return jsonify({"mothers": result, "total": len(result)}), 200


@bp.route('/chws/<int:chw_id>/assign_mother', methods=['POST'])
def assign_mother_to_chw(chw_id):
    """Assign a mother to a CHW (max 20 active per CHW)."""
    data = request.get_json() or {}
    mother_id = data.get('mother_id')
    if not mother_id:
        return jsonify({"error": "mother_id is required."}), 400

    chw = CHW.query.get(chw_id)
    if not chw:
        user = User.query.get(chw_id)
        if user and user.role == 'chw':
            return jsonify({
                "error": (
                    f"CHW profile not found for user {chw_id}. "
                    "The CHW registered but their profile was not created. "
                    "Please contact support or re-register."
                )
            }), 404
        return jsonify({"error": f"CHW with id {chw_id} not found."}), 404

    mother = Mother.query.get(mother_id)
    if not mother:
        return jsonify({"error": f"Mother with id {mother_id} not found."}), 404

    # Prevent duplicate ACTIVE assignment
    existing = MotherCHWAssignment.query.filter_by(
        chw_id=chw_id, mother_id=mother_id, status='active'
    ).first()
    if existing:
        return jsonify({"error": "Mother is already actively assigned to this CHW."}), 409

    # Enforce max 20 ACTIVE mothers per CHW
    active_count = MotherCHWAssignment.query.filter_by(chw_id=chw_id, status='active').count()
    if active_count >= 20:
        return jsonify({"error": "CHW has reached the maximum of 20 active mother assignments."}), 400

    # Re-activate if an inactive record already exists (avoids unique constraint violation)
    inactive = MotherCHWAssignment.query.filter_by(
        chw_id=chw_id, mother_id=mother_id, status='inactive'
    ).first()
    if inactive:
        inactive.status = 'active'
        inactive.assigned_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"message": "Assignment reactivated.", **_serialize_assignment(inactive)}), 200

    try:
        assignment = MotherCHWAssignment(
            chw_id=chw_id,
            mother_id=mother_id,
            chw_name=chw.chw_name,
            mother_name=mother.mother_name,
            status='active',
        )
        db.session.add(assignment)
        db.session.commit()
        return jsonify({"message": "Mother assigned to CHW successfully.",
                        **_serialize_assignment(assignment)}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Assignment failed: {str(e)}"}), 500


@bp.route('/assignments/<int:assignment_id>/status', methods=['PATCH'])
def update_assignment_status(assignment_id):
    """Activate or deactivate an assignment.  Body: { "status": "active" | "inactive" }"""
    data = request.get_json() or {}
    new_status = data.get('status')
    if new_status not in ('active', 'inactive'):
        return jsonify({"error": "status must be 'active' or 'inactive'."}), 400
    assignment = MotherCHWAssignment.query.get(assignment_id)
    if not assignment:
        return jsonify({"error": "Assignment not found."}), 404
    assignment.status = new_status
    db.session.commit()
    return jsonify({"message": f"Assignment status updated to '{new_status}'.",
                    **_serialize_assignment(assignment)}), 200


@bp.route('/assignments/<int:assignment_id>', methods=['DELETE'])
def delete_assignment(assignment_id):
    """Permanently delete an assignment record."""
    assignment = MotherCHWAssignment.query.get(assignment_id)
    if not assignment:
        return jsonify({"error": "Assignment not found."}), 404
    db.session.delete(assignment)
    db.session.commit()
    return jsonify({"message": "Assignment deleted."}), 200


# ── Nurse / admin list endpoints ──────────────────────────────────────────────

@bp.route('/nurses/<int:nurse_id>/assignments', methods=['GET'])
def get_assignments_for_nurse(nurse_id):
    """All mother-CHW assignments for CHWs in the same ward as the nurse."""
    nurse = Nurse.query.get(nurse_id)
    if not nurse:
        return jsonify({"error": f"Nurse with id {nurse_id} not found."}), 404

    chws_in_ward = CHW.query.filter_by(ward_id=nurse.ward_id).all()
    chw_ids = [c.id for c in chws_in_ward]

    status_filter = request.args.get('status')
    q = MotherCHWAssignment.query.filter(MotherCHWAssignment.chw_id.in_(chw_ids))
    if status_filter:
        q = q.filter_by(status=status_filter)

    assignments = q.order_by(MotherCHWAssignment.assigned_at.desc()).all()
    return jsonify({
        "assignments": [_serialize_assignment(a) for a in assignments],
        "total": len(assignments),
    }), 200


# ── Mother endpoints ──────────────────────────────────────────────────────────

@bp.route('/mothers/<int:user_id>/assigned_chw', methods=['GET'])
def get_assigned_chw_for_mother(user_id):
    """
    Get the CHW assigned to a mother (by mother's user_id).
    Returns the CHW's user_id and profile details.
    """
    # Find mother profile by user_id
    mother = Mother.query.filter_by(user_id=user_id).first()
    if not mother:
        return jsonify({"error": f"Mother profile for user {user_id} not found."}), 404

    # Find active assignment
    assignment = MotherCHWAssignment.query.filter_by(
        mother_id=mother.id, status='active'
    ).first()
    if not assignment:
        return jsonify({
            "assigned": False,
            "message": "No active CHW assignment for this mother."
        }), 200

    # Get CHW profile
    chw = CHW.query.get(assignment.chw_id)
    if not chw:
        return jsonify({
            "assigned": False,
            "error": "CHW profile not found for assignment."
        }), 404

    # Get CHW user for phone number
    chw_user = User.query.get(chw.user_id)

    return jsonify({
        "assigned": True,
        "chw": {
            "user_id": chw.user_id,
            "profile_id": chw.id,
            "name": chw.chw_name,
            "phone": chw_user.phone_number if chw_user else None,
            "location": chw.location,
        },
        "assignment_id": assignment.id,
        "assigned_at": assignment.assigned_at.isoformat() if assignment.assigned_at else None,
    }), 200


@bp.route('/assignments', methods=['GET'])
def list_all_assignments():
    """List assignments.  Optional ?chw_id=&mother_id=&status="""
    q = MotherCHWAssignment.query
    if chw_id := request.args.get('chw_id', type=int):
        q = q.filter_by(chw_id=chw_id)
    if mother_id := request.args.get('mother_id', type=int):
        q = q.filter_by(mother_id=mother_id)
    if status := request.args.get('status'):
        q = q.filter_by(status=status)
    assignments = q.order_by(MotherCHWAssignment.assigned_at.desc()).all()
    return jsonify({
        "assignments": [_serialize_assignment(a) for a in assignments],
        "total": len(assignments),
    }), 200
