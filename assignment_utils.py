from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func

from app import db
from models import CHW, Mother, User
from models_standard import MotherCHWAssignment
from notifications import create_user_notification
from socket_manager import socketio


ASSIGNMENT_METHOD_AUTO_WARD_MATCH = 'auto_ward_match'
ASSIGNMENT_METHOD_MANUAL = 'manual'
MAX_ACTIVE_MOTHERS_PER_CHW = 20


class AssignmentConflictError(Exception):
    pass


class AssignmentCapacityError(Exception):
    pass


def serialize_assignment(assignment: MotherCHWAssignment):
    return {
        "id": assignment.id,
        "mother_id": assignment.mother_id,
        "mother_name": assignment.mother_name,
        "chw_id": assignment.chw_id,
        "chw_name": assignment.chw_name,
        "assigned_at": assignment.assigned_at.isoformat() if assignment.assigned_at else None,
        "status": assignment.status,
        "assignment_method": assignment.assignment_method,
        "reassigned_at": assignment.reassigned_at.isoformat() if assignment.reassigned_at else None,
        "reassignment_reason": assignment.reassignment_reason,
    }


def emit_assignment_event(event: str, assignment: MotherCHWAssignment, mother: Mother | None = None):
    payload = serialize_assignment(assignment)
    title_by_event = {
        "assignment:created": "New Mother Assignment",
        "assignment:status_changed": "Assignment Status Changed",
        "assignment:deleted": "Assignment Removed",
    }
    title = title_by_event.get(event, "Assignment Update")
    message = f"{assignment.mother_name} assignment has been updated."

    socketio.emit(event, payload, to=f"chw:{assignment.chw_id}")

    chw = CHW.query.get(assignment.chw_id)
    if chw:
        socketio.emit(event, payload, to=f"user:{chw.user_id}")
        create_user_notification(
            user_id=chw.user_id,
            event_type=event,
            title=title,
            message=message,
            url="/dashboard/chw",
            entity_type="assignment",
            entity_id=assignment.id,
        )

    if mother is None:
        mother = Mother.query.get(assignment.mother_id)
    if mother:
        socketio.emit(event, payload, to=f"user:{mother.user_id}")
        create_user_notification(
            user_id=mother.user_id,
            event_type=event,
            title=title,
            message="Your CHW assignment has been updated.",
            url="/dashboard/mother",
            entity_type="assignment",
            entity_id=assignment.id,
        )


def get_active_assignment_for_mother(mother_id: int):
    return MotherCHWAssignment.query.filter_by(mother_id=mother_id, status='active').first()


def count_active_assignments_for_chw(chw_id: int) -> int:
    return MotherCHWAssignment.query.filter_by(chw_id=chw_id, status='active').count()


def find_best_chw_for_ward(ward_id: int, exclude_chw_ids: set[int] | None = None):
    exclude_chw_ids = exclude_chw_ids or set()
    chws = CHW.query.filter_by(ward_id=ward_id).order_by(CHW.id.asc()).all()
    if not chws:
        return None

    active_counts = {
        chw_id: count
        for chw_id, count in (
            db.session.query(MotherCHWAssignment.chw_id, func.count(MotherCHWAssignment.id))
            .filter(
                MotherCHWAssignment.status == 'active',
                MotherCHWAssignment.chw_id.in_([chw.id for chw in chws]),
            )
            .group_by(MotherCHWAssignment.chw_id)
            .all()
        )
    }

    best = None
    best_count = None
    for chw in chws:
        if chw.id in exclude_chw_ids:
            continue
        count = int(active_counts.get(chw.id, 0))
        if count >= MAX_ACTIVE_MOTHERS_PER_CHW:
            continue
        if best is None or count < best_count or (count == best_count and chw.id < best.id):
            best = chw
            best_count = count

    return best


def _deactivate_assignment(assignment: MotherCHWAssignment, reason: str | None = None):
    assignment.status = 'inactive'
    assignment.reassigned_at = datetime.now(timezone.utc)
    assignment.reassignment_reason = reason


def assign_mother_to_specific_chw(
    chw: CHW,
    mother: Mother,
    *,
    assignment_method: str,
    conflict_policy: str = 'refuse',
    reassignment_reason: str | None = None,
):
    now = datetime.now(timezone.utc)

    current_active = get_active_assignment_for_mother(mother.id)
    if current_active:
        if current_active.chw_id == chw.id:
            return current_active, False, 'already_active'
        if conflict_policy == 'refuse':
            raise AssignmentConflictError("Mother already has an active CHW assignment.")
        _deactivate_assignment(current_active, reassignment_reason or 'active_assignment_replaced')
        db.session.flush()

    if count_active_assignments_for_chw(chw.id) >= MAX_ACTIVE_MOTHERS_PER_CHW:
        raise AssignmentCapacityError("CHW has reached the maximum of 20 active mother assignments.")

    existing_pair = (
        MotherCHWAssignment.query
        .filter_by(chw_id=chw.id, mother_id=mother.id)
        .order_by(MotherCHWAssignment.id.desc())
        .first()
    )
    if existing_pair:
        existing_pair.status = 'active'
        existing_pair.assigned_at = now
        existing_pair.chw_name = chw.chw_name
        existing_pair.mother_name = mother.mother_name
        existing_pair.assignment_method = assignment_method
        existing_pair.reassigned_at = now if reassignment_reason else existing_pair.reassigned_at
        existing_pair.reassignment_reason = reassignment_reason
        return existing_pair, True, 'reactivated'

    assignment = MotherCHWAssignment(
        chw_id=chw.id,
        mother_id=mother.id,
        chw_name=chw.chw_name,
        mother_name=mother.mother_name,
        status='active',
        assignment_method=assignment_method,
        reassigned_at=now if reassignment_reason else None,
        reassignment_reason=reassignment_reason,
    )
    db.session.add(assignment)
    db.session.flush()
    return assignment, True, 'created'


def assign_mother_if_possible(
    mother_id: int,
    *,
    assignment_method: str = ASSIGNMENT_METHOD_AUTO_WARD_MATCH,
    exclude_chw_ids: set[int] | None = None,
    conflict_policy: str = 'replace',
    reassignment_reason: str | None = None,
):
    mother = Mother.query.get(mother_id)
    if not mother or not mother.ward_id:
        return None, False

    current_active = get_active_assignment_for_mother(mother.id)
    if current_active and (exclude_chw_ids is None or current_active.chw_id not in exclude_chw_ids):
        return current_active, False

    chw = find_best_chw_for_ward(mother.ward_id, exclude_chw_ids=exclude_chw_ids)
    if not chw:
        return None, False

    assignment, changed, _status = assign_mother_to_specific_chw(
        chw,
        mother,
        assignment_method=assignment_method,
        conflict_policy=conflict_policy,
        reassignment_reason=reassignment_reason,
    )
    return assignment, changed


def backfill_chw_from_ward_backlog(
    chw_id: int,
    *,
    assignment_method: str = ASSIGNMENT_METHOD_AUTO_WARD_MATCH,
):
    chw = CHW.query.get(chw_id)
    if not chw or not chw.ward_id:
        return []

    available_slots = MAX_ACTIVE_MOTHERS_PER_CHW - count_active_assignments_for_chw(chw.id)
    if available_slots <= 0:
        return []

    active_mother_ids_subquery = (
        db.session.query(MotherCHWAssignment.mother_id)
        .filter(MotherCHWAssignment.status == 'active')
    )
    mothers = (
        Mother.query
        .filter(Mother.ward_id == chw.ward_id)
        .filter(~Mother.id.in_(active_mother_ids_subquery))
        .order_by(Mother.created_at.asc(), Mother.id.asc())
        .limit(available_slots)
        .all()
    )

    created_assignments = []
    for mother in mothers:
        assignment, changed, _status = assign_mother_to_specific_chw(
            chw,
            mother,
            assignment_method=assignment_method,
            conflict_policy='replace',
        )
        if changed:
            created_assignments.append(assignment)

    return created_assignments


def reassign_mothers_for_chw(
    chw_id: int,
    *,
    reassignment_reason: str = 'chw_unavailable_same_ward_reassignment',
):
    active_assignments = (
        MotherCHWAssignment.query
        .filter_by(chw_id=chw_id, status='active')
        .order_by(MotherCHWAssignment.assigned_at.asc(), MotherCHWAssignment.id.asc())
        .all()
    )
    if not active_assignments:
        return []

    mothers = []
    for assignment in active_assignments:
        _deactivate_assignment(assignment, reassignment_reason)
        mother = Mother.query.get(assignment.mother_id)
        if mother:
            mothers.append(mother)

    db.session.flush()

    new_assignments = []
    for mother in mothers:
        assignment, changed = assign_mother_if_possible(
            mother.id,
            assignment_method=ASSIGNMENT_METHOD_AUTO_WARD_MATCH,
            exclude_chw_ids={chw_id},
            conflict_policy='replace',
            reassignment_reason=reassignment_reason,
        )
        if changed and assignment:
            new_assignments.append(assignment)

    return new_assignments
