from collections import defaultdict
from datetime import datetime, timedelta, timezone
from functools import wraps
from math import atan2, cos, radians, sin, sqrt
import re
import secrets

from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt_identity, verify_jwt_in_request
from sqlalchemy import func, or_

from app import db
from africas_talking_service import get_otp_service, send_otp
from auth_utils import generate_otp, hash_pin, verify_pin
from models import (
    CHW,
    AppointmentTicketEvent,
    DailyCheckin,
    FacilityAccount,
    FacilityAppointment,
    FacilityEscalation,
    FacilityInvitation,
    FacilityStaff,
    HealthFacility,
    Mother,
    OTPToken,
    Resource,
    SubCounty,
    UltrasoundRecord,
    User,
    UserNotification,
    Ward,
)
from notifications import create_user_notification, send_push
from push_payloads import build_push_data
from socket_manager import socketio

bp = Blueprint('facility_staff_auth', __name__)

ALLOWED_STAFF_ROLES = {'admin', 'doctor', 'nurse'}
ALLOWED_STAFF_STATUSES = {'pending_verification', 'active', 'inactive', 'removed'}
ASSIGNABLE_MEMBER_ROLES = {'doctor', 'nurse'}
FACILITY_ESCALATION_STATUSES = {'received', 'in_progress', 'checked_out'}
FACILITY_ESCALATION_STATUS_ALIASES = {
    'received': 'received',
    'in_progress': 'in_progress',
    'inprogress': 'in_progress',
    'checked_out': 'checked_out',
    'checkedout': 'checked_out',
}
NURSE_COMPAT_MEMBER_ROLES = {'admin', 'doctor', 'nurse'}
NURSE_COMPAT_TO_FACILITY_STATUS = {
    'pending': 'received',
    'in_progress': 'in_progress',
    'resolved': 'checked_out',
    'rejected': 'checked_out',
}
FACILITY_TO_NURSE_COMPAT_STATUS = {
    'received': 'pending',
    'in_progress': 'in_progress',
    'checked_out': 'resolved',
}
NURSE_COMPAT_HIDDEN_NOTE_MARKER = '[hidden_by_nurse_compat]'
VALID_RELEVANCE_PROFILES = {'maternal_referral', 'all'}
MATERNAL_REFERRAL_AMENITIES = {'hospital', 'clinic', 'doctors', 'health_centre'}
MATERNAL_REFERRAL_HEALTHCARE_TOKENS = {
    'hospital',
    'clinic',
    'maternity',
    'obstetric',
    'gynaecology',
    'gynecology',
    'paediatrics',
    'pediatrics',
    'midwife',
    'general',
    'emergency',
}
MIN_APPOINTMENT_LEAD_TIME = timedelta(hours=1)


def normalize_phone_number(phone):
    phone = (phone or '').strip()
    cleaned = re.sub(r'[^0-9]', '', phone)

    if cleaned.startswith('07') and len(cleaned) == 10:
        return '+254' + cleaned[1:]

    if cleaned.startswith('254') and len(cleaned) == 12:
        return '+' + cleaned

    if phone.startswith('+254') and len(re.sub(r'[^0-9]', '', phone)) == 12:
        return '+254' + re.sub(r'[^0-9]', '', phone)[3:]

    return phone


def _is_normalized_kenyan_phone(phone):
    return bool(re.match(r'^\+254[0-9]{9}$', (phone or '').strip()))


def _normalize_facility_escalation_status(value):
    incoming = (value or '').strip().lower()
    return FACILITY_ESCALATION_STATUS_ALIASES.get(incoming)


def _facility_identity(account_id: int) -> str:
    return f'facility:{account_id}'


def _resolve_facility_account_from_jwt():
    verify_jwt_in_request()
    identity = str(get_jwt_identity() or '')

    if not identity.startswith('facility:'):
        return None

    account_id_str = identity.split(':', 1)[1]
    try:
        account_id = int(account_id_str)
    except ValueError:
        return None

    account = FacilityAccount.query.get(account_id)
    if not account or not account.is_active:
        return None

    return account


def _find_facility_account_by_contact(phone_number=None, email=None):
    account = None
    if phone_number:
        account = FacilityAccount.query.filter_by(phone_number=phone_number).first()
    if not account and email:
        account = FacilityAccount.query.filter_by(email=email).first()
    return account


def require_facility_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            account = _resolve_facility_account_from_jwt()
        except Exception:
            return jsonify({'error': 'Invalid or expired token'}), 401

        if not account:
            return jsonify({'error': 'Facility authentication required'}), 401

        request.current_facility_account = account
        return f(*args, **kwargs)

    return decorated


def _auth_payload_for_account(account: FacilityAccount):
    first_name = (account.first_name or '').strip()
    last_name = (account.last_name or '').strip()
    profile_completed = bool(account.profile_completed)
    display_name = f'{first_name} {last_name}'.strip()
    if not display_name and not profile_completed:
        display_name = 'Pending profile'

    return {
        'id': account.id,
        'phone_number': account.phone_number,
        'email': account.email,
        'first_name': first_name,
        'last_name': last_name,
        'name': display_name,
        'role': 'facility_staff',
        'account_role': account.role,
        'profile_completed': profile_completed,
        'facility_id': account.facility_id,
    }


def _active_membership(account_id, facility_id=None):
    query = FacilityStaff.query.filter_by(account_id=account_id, status='active')
    if facility_id:
        query = query.filter_by(facility_id=facility_id)
    return query.first()


def _admin_facility_for_account(account, facility_id=None):
    query = HealthFacility.query.filter_by(facility_admin_id=account.id)
    if facility_id:
        query = query.filter_by(id=facility_id)
    return query.first()


def _parse_iso_datetime(value):
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception:
        return None

def _resolve_mother_for_appointment(mother_id=None, mother_phone_number=None):
    if mother_phone_number:
        normalized_phone = normalize_phone_number(mother_phone_number)
        if not _is_normalized_kenyan_phone(normalized_phone):
            return None, None, (jsonify({'error': 'Please enter mother_phone_number in 07xxxxxxxx format'}), 400)

        mother_user = User.query.filter_by(phone_number=normalized_phone, role='mother').first()
        if not mother_user:
            return None, None, (jsonify({'error': 'Mother with the provided phone number was not found'}), 404)

        mother_profile = Mother.query.filter_by(user_id=mother_user.id).first()
        if not mother_profile:
            return None, None, (jsonify({'error': 'Mother profile for the provided phone number was not found'}), 404)

        resolved_name = (mother_profile.mother_name or mother_user.name or 'Mother').strip()
        return mother_user.id, resolved_name, None

    if mother_id:
        mother_user = User.query.get(mother_id)
        if not mother_user:
            return None, None, (jsonify({'error': 'Mother not found'}), 404)

        mother_profile = Mother.query.filter_by(user_id=mother_user.id).first()
        resolved_name = (
            (mother_profile.mother_name if mother_profile else None)
            or mother_user.name
            or f"{mother_user.first_name} {mother_user.last_name}".strip()
            or 'Mother'
        ).strip()
        return mother_user.id, resolved_name, None

    return None, None, (jsonify({'error': 'mother_id or mother_phone_number is required'}), 400)

def _normalize_to_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def _validate_minimum_schedule_time(scheduled_time):
    scheduled_time_utc = _normalize_to_utc(scheduled_time)
    now = datetime.now(timezone.utc)
    minimum_time = now + MIN_APPOINTMENT_LEAD_TIME
    if scheduled_time_utc < minimum_time:
        return jsonify({'error': 'Appointments must be scheduled at least 1 hour from the current time.'}), 400
    return None

def _generate_ticket_code(prefix, exists_callback):
    while True:
        code = f"{prefix}-{secrets.token_hex(3).upper()}"
        if not exists_callback(code):
            return code

def _create_facility_appointment_ticket_code():
    return _generate_ticket_code(
        'RCC-FAC',
        lambda code: FacilityAppointment.query.filter_by(ticket_code=code).first() is not None
    )

def _apply_facility_ticket_state_for_status(appointment, status, actor_account_id=None, validation_method=None):
    if status == 'canceled':
        appointment.ticket_status = 'canceled'
        appointment.validated_at = None
        appointment.validated_by_account_id = None
        appointment.validation_method = None
    elif status == 'completed':
        appointment.ticket_status = 'used'
        appointment.validated_at = datetime.now(timezone.utc)
        appointment.validated_by_account_id = actor_account_id
        appointment.validation_method = validation_method or 'manual'
    else:
        appointment.ticket_status = 'active'
        appointment.validated_at = None
        appointment.validated_by_account_id = None
        appointment.validation_method = None

def _log_facility_ticket_event(appointment, event_type, actor_account_id=None, actor_role=None, metadata=None, notes=None):
    event = AppointmentTicketEvent(
        appointment_source='facility',
        appointment_id=appointment.id,
        ticket_code=appointment.ticket_code,
        event_type=event_type,
        actor_facility_account_id=actor_account_id,
        actor_role=actor_role,
        metadata_json=metadata or {},
        notes=notes,
    )
    appointment.ticket_last_event_at = datetime.now(timezone.utc)
    db.session.add(event)


def _distance_km_from_wkt(geometry_wkt: str | None, lat: float, lng: float):
    if not geometry_wkt:
        return None

    try:
        match = re.search(r'POINT\(([^ ]+) ([^ ]+)\)', geometry_wkt)
        if not match:
            return None

        facility_lng = float(match.group(1))
        facility_lat = float(match.group(2))

        lat1, lng1 = radians(facility_lat), radians(facility_lng)
        lat2, lng2 = radians(lat), radians(lng)

        dlat = lat2 - lat1
        dlng = lng2 - lng1

        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        return round(6371 * c, 2)
    except Exception:
        return None


def _normalize_csv_param(raw_value: str | None, default_values=None):
    if raw_value is None:
        values = list(default_values or [])
    else:
        values = [value.strip().lower() for value in raw_value.split(',') if value.strip()]

    deduped = []
    seen = set()
    for value in values:
        if value not in seen:
            deduped.append(value)
            seen.add(value)
    return deduped


def _resolve_relevance_profile(raw_profile: str | None, amenity_values):
    profile = (raw_profile or 'maternal_referral').strip().lower()
    if profile not in VALID_RELEVANCE_PROFILES:
        profile = 'maternal_referral'

    # If client explicitly asks for non-referral amenity types (e.g. pharmacy),
    # honor that intent by widening to full discovery mode.
    if profile == 'maternal_referral' and amenity_values:
        if all(value not in MATERNAL_REFERRAL_AMENITIES for value in amenity_values):
            return 'all'

    return profile


def _apply_relevance_profile(query, profile: str):
    if profile == 'all':
        return query

    healthcare_clauses = [HealthFacility.healthcare.ilike(f'%{token}%') for token in MATERNAL_REFERRAL_HEALTHCARE_TOKENS]

    return query.filter(
        or_(
            HealthFacility.amenity.in_(sorted(MATERNAL_REFERRAL_AMENITIES)),
            or_(*healthcare_clauses),
            HealthFacility.name.ilike('%maternity%'),
            HealthFacility.name.ilike('%maternal%'),
            HealthFacility.name.ilike('%women%'),
        )
    )


def _emit_facility_appointment(event_name: str, facility_id: int, appointment: FacilityAppointment):
    payload = appointment.to_dict()
    socketio.emit(event_name, payload, to=f'facility:{facility_id}')

    if appointment.assigned_staff_account_id:
        socketio.emit(event_name, payload, to=f'facility_account:{appointment.assigned_staff_account_id}')

    if appointment.mother_id:
        socketio.emit(event_name, payload, to=f'user:{appointment.mother_id}')


def _emit_facility_staff_update(facility_id: int):
    rows = FacilityStaff.query.filter_by(facility_id=facility_id).order_by(FacilityStaff.added_at.desc()).all()
    socketio.emit('facility:staff_update', {
        'facility_id': facility_id,
        'count': len(rows),
        'staff': [row.to_dict() for row in rows],
    }, to=f'facility:{facility_id}')


def _resolve_facility_scope(account: FacilityAccount, facility_id: int | None):
    admin_facility = _admin_facility_for_account(account, facility_id)
    if admin_facility:
        return admin_facility.id, True, _active_membership(account.id, admin_facility.id)

    membership = _active_membership(account.id, facility_id)
    if membership:
        return membership.facility_id, False, membership

    return jsonify({'error': 'Access denied for this facility'}), 403


def _escalation_payload_with_permissions(escalation: FacilityEscalation, is_admin: bool):
    payload = escalation.to_dict()
    payload['permissions'] = {
        'can_assign': bool(is_admin),
        'can_update_status': bool(is_admin),
        'can_edit': bool(is_admin),
        'can_comment': True,
    }
    return payload


def _emit_facility_escalation(event_name: str, escalation: FacilityEscalation):
    payload = escalation.to_dict()
    socketio.emit(event_name, payload, to=f'facility:{escalation.facility_id}')

    if escalation.assigned_staff_account_id:
        socketio.emit(event_name, payload, to=f'facility_account:{escalation.assigned_staff_account_id}')

    if escalation.mother_user_id:
        socketio.emit(event_name, payload, to=f'user:{escalation.mother_user_id}')

    if escalation.chw_user_id:
        socketio.emit(event_name, payload, to=f'user:{escalation.chw_user_id}')


def _notify_facility_escalation_status_change(escalation: FacilityEscalation):
    status_text = escalation.status.replace('_', ' ')
    if escalation.mother_user_id:
        create_user_notification(
            user_id=escalation.mother_user_id,
            event_type='facility:escalation_updated',
            title='Facility Escalation Update',
            message=f"Your case is now '{status_text}' at {escalation.facility.name if escalation.facility else 'the facility'}.",
            url='/dashboard/mother',
            entity_type='facility_escalation',
            entity_id=escalation.id,
        )
        send_push(
            escalation.mother_user_id,
            'Facility Escalation Update',
            f"Your case is now '{status_text}'.",
            build_push_data(
                event='facility:escalation_updated',
                url='/dashboard/mother',
                entity_type='facility_escalation',
                entity_id=escalation.id,
                role='mother',
                extra={
                    'status': escalation.status,
                    'facility_name': escalation.facility.name if escalation.facility else '',
                    'facility_phone': escalation.facility.phone if escalation.facility else '',
                },
            ),
        )

    if escalation.chw_user_id:
        create_user_notification(
            user_id=escalation.chw_user_id,
            event_type='facility:escalation_updated',
            title='Facility Escalation Update',
            message=f"Escalated case for {escalation.mother_name} is now '{status_text}'.",
            url='/dashboard/chw',
            entity_type='facility_escalation',
            entity_id=escalation.id,
        )
        send_push(
            escalation.chw_user_id,
            'Facility Escalation Update',
            f"{escalation.mother_name}'s case is now '{status_text}'.",
            build_push_data(
                event='facility:escalation_updated',
                url='/dashboard/chw',
                entity_type='facility_escalation',
                entity_id=escalation.id,
                role='chw',
                extra={
                    'status': escalation.status,
                    'facility_name': escalation.facility.name if escalation.facility else '',
                    'facility_phone': escalation.facility.phone if escalation.facility else '',
                },
            ),
        )


def _resolve_user_for_facility_account(account: FacilityAccount | None):
    if not account:
        return None

    if account.phone_number:
        user = User.query.filter_by(phone_number=account.phone_number).first()
        if user:
            return user

    if account.email:
        user = User.query.filter_by(email=account.email).first()
        if user:
            return user

    return None


def _format_legacy_nurse_location(facility: HealthFacility | None):
    if not facility:
        return None
    return (facility.city or facility.address or '').strip() or None


def _ensure_nurse_compat_scope(account: FacilityAccount, facility_id: int):
    resolved = _resolve_facility_scope(account, facility_id)
    if len(resolved) != 3:
        return resolved

    resolved_facility_id, is_admin, membership = resolved
    role = 'admin' if is_admin else ((membership.role if membership else account.role) or '').strip().lower()
    if role not in NURSE_COMPAT_MEMBER_ROLES:
        return jsonify({'error': 'Nurse compatibility mode only supports admin, nurse, and doctor members'}), 403

    return resolved_facility_id, is_admin, membership, role


def _serialize_nurse_compat_escalation(row: FacilityEscalation):
    return {
        'id': row.id,
        'chw_id': row.chw_id,
        'chw_name': row.chw.name if row.chw else None,
        'nurse_id': row.assigned_staff_account_id or row.updated_by_account_id,
        'nurse_name': row.assigned_staff.name if row.assigned_staff else None,
        'mother_id': row.mother_id,
        'checkin_id': row.checkin_id,
        'mother_name': row.mother_name,
        'case_description': row.case_description,
        'issue_type': row.issue_type,
        'notes': row.notes,
        'priority': row.priority,
        'status': FACILITY_TO_NURSE_COMPAT_STATUS.get(row.status, 'pending'),
        'created_at': row.created_at.isoformat() if row.created_at else None,
        'resolved_at': row.checked_out_at.isoformat() if row.checked_out_at else None,
        'facility_id': row.facility_id,
    }


def _nurse_compat_escalation_is_hidden(row: FacilityEscalation):
    return NURSE_COMPAT_HIDDEN_NOTE_MARKER in ((row.notes or '').strip())


def _nurse_compat_mark_hidden(notes: str | None):
    current = (notes or '').strip()
    if NURSE_COMPAT_HIDDEN_NOTE_MARKER in current:
        return current
    return f"{current} {NURSE_COMPAT_HIDDEN_NOTE_MARKER}".strip()


def _nurse_compat_unmark_hidden(notes: str | None):
    current = (notes or '').replace(NURSE_COMPAT_HIDDEN_NOTE_MARKER, '').strip()
    return current or None


def _serialize_nurse_compat_appointment(row: FacilityAppointment):
    assigned_user = _resolve_user_for_facility_account(row.assigned_staff)
    creator_user = _resolve_user_for_facility_account(row.creator_account)

    return {
        'id': row.id,
        'mother_id': row.mother_id,
        'health_worker_id': assigned_user.id if assigned_user else None,
        'created_by_user_id': creator_user.id if creator_user else None,
        'mother_name': row.mother_name,
        'hw_name': row.assigned_staff.name if row.assigned_staff else None,
        'creator_name': row.creator_account.name if row.creator_account else None,
        'scheduled_time': row.scheduled_time.isoformat() if row.scheduled_time else None,
        'appointment_type': row.appointment_type,
        'recurrence_rule': None,
        'recurrence_end': None,
        'status': row.status,
        'escalated': False,
        'escalation_reason': None,
        'notes': row.notes,
        'ticket_code': row.ticket_code,
        'ticket_status': row.ticket_status,
        'validated_at': row.validated_at.isoformat() if row.validated_at else None,
        'validated_by_account_id': row.validated_by_account_id,
        'validation_method': row.validation_method,
        'ticket_last_event_at': row.ticket_last_event_at.isoformat() if row.ticket_last_event_at else None,
        'created_at': row.created_at.isoformat() if row.created_at else None,
        'updated_at': row.updated_at.isoformat() if row.updated_at else None,
    }


def _serialize_user_notification(row: UserNotification):
    return {
        'id': row.id,
        'event_type': row.event_type,
        'title': row.title,
        'message': row.message,
        'url': row.url,
        'entity_type': row.entity_type,
        'entity_id': row.entity_id,
        'is_read': bool(row.is_read),
        'read_at': row.read_at.isoformat() if row.read_at else None,
        'created_at': row.created_at.isoformat() if row.created_at else None,
    }


def _notify_mother_facility_appointment(appointment: FacilityAppointment, event_name: str):
    if not appointment.mother_id:
        return

    if event_name == 'facility:appointment_created':
        title = 'Facility Appointment Scheduled'
        message = f"Your appointment with {appointment.facility.name if appointment.facility else 'the facility'} has been scheduled."
    else:
        title = 'Facility Appointment Update'
        message = f"Your appointment status is now '{appointment.status}'."

    create_user_notification(
        user_id=appointment.mother_id,
        event_type=event_name,
        title=title,
        message=message,
        url='/dashboard/mother',
        entity_type='facility_appointment',
        entity_id=appointment.id,
    )

    send_push(
        appointment.mother_id,
        title,
        message,
        build_push_data(
            event=event_name,
            url='/dashboard/mother',
            entity_type='facility_appointment',
            entity_id=appointment.id,
            role='mother',
            extra={
                'facility_id': appointment.facility_id,
                'facility_name': appointment.facility.name if appointment.facility else '',
                'status': appointment.status,
                'scheduled_time': appointment.scheduled_time.isoformat() if appointment.scheduled_time else '',
            },
        ),
    )


def _notify_facility_admin_for_new_appointment(appointment: FacilityAppointment):
    if not appointment.facility or not appointment.facility.admin:
        return

    admin_user = _resolve_user_for_facility_account(appointment.facility.admin)
    if not admin_user:
        return

    create_user_notification(
        user_id=admin_user.id,
        event_type='facility:appointment_created',
        title='New Facility Appointment',
        message=f"New appointment for {appointment.mother_name} at your facility.",
        url='/dashboard/facility',
        entity_type='facility_appointment',
        entity_id=appointment.id,
    )

    send_push(
        admin_user.id,
        'New Facility Appointment',
        f"New appointment for {appointment.mother_name}.",
        build_push_data(
            event='facility:appointment_created',
            url='/dashboard/facility',
            entity_type='facility_appointment',
            entity_id=appointment.id,
            role='facility_staff',
            extra={
                'facility_id': appointment.facility_id,
                'mother_name': appointment.mother_name,
                'status': appointment.status,
            },
        ),
    )


def _notify_assigned_facility_staff_for_appointment(appointment: FacilityAppointment):
    if not appointment.assigned_staff_account_id:
        return

    target_user = _resolve_user_for_facility_account(appointment.assigned_staff)
    if not target_user:
        return

    create_user_notification(
        user_id=target_user.id,
        event_type='facility:appointment_updated',
        title='Facility Appointment Assigned',
        message=f"You are assigned to {appointment.mother_name}'s appointment.",
        url='/dashboard/facility',
        entity_type='facility_appointment',
        entity_id=appointment.id,
    )

    send_push(
        target_user.id,
        'Facility Appointment Assigned',
        f"You are assigned to {appointment.mother_name}'s appointment.",
        build_push_data(
            event='facility:appointment_updated',
            url='/dashboard/facility',
            entity_type='facility_appointment',
            entity_id=appointment.id,
            role='facility_staff',
            extra={
                'facility_id': appointment.facility_id,
                'mother_name': appointment.mother_name,
                'status': appointment.status,
            },
        ),
    )


def _notify_facility_staff_assignment(escalation: FacilityEscalation, assigned_account: FacilityAccount, actor_account: FacilityAccount):
    target_user = _resolve_user_for_facility_account(assigned_account)
    if not target_user:
        return

    create_user_notification(
        user_id=target_user.id,
        event_type='facility:escalation_assigned',
        title='New Facility Escalation Assignment',
        message=f"You were assigned a case for {escalation.mother_name}.",
        url='/dashboard/facility',
        entity_type='facility_escalation',
        entity_id=escalation.id,
    )

    send_push(
        target_user.id,
        'New Escalation Assignment',
        f"Case for {escalation.mother_name} assigned to you.",
        build_push_data(
            event='facility:escalation_assigned',
            url='/dashboard/facility',
            entity_type='facility_escalation',
            entity_id=escalation.id,
            role='facility_staff',
            extra={
                'facility_id': escalation.facility_id,
                'facility_name': escalation.facility.name if escalation.facility else '',
                'assigned_staff_role': escalation.assigned_staff_role or assigned_account.role,
                'assigned_by': actor_account.name,
                'status': escalation.status,
            },
        ),
    )


def _notify_facility_admin_status_update(escalation: FacilityEscalation, actor_account: FacilityAccount):
    facility_admin_account = escalation.facility.admin if escalation.facility else None
    if not facility_admin_account or facility_admin_account.id == actor_account.id:
        return

    admin_user = _resolve_user_for_facility_account(facility_admin_account)
    if not admin_user:
        return

    status_text = escalation.status.replace('_', ' ')
    create_user_notification(
        user_id=admin_user.id,
        event_type='facility:escalation_updated',
        title='Facility Escalation Status Updated',
        message=f"Case for {escalation.mother_name} is now '{status_text}'.",
        url='/dashboard/facility',
        entity_type='facility_escalation',
        entity_id=escalation.id,
    )

    send_push(
        admin_user.id,
        'Escalation Status Updated',
        f"Case for {escalation.mother_name} is now '{status_text}'.",
        build_push_data(
            event='facility:escalation_updated',
            url='/dashboard/facility',
            entity_type='facility_escalation',
            entity_id=escalation.id,
            role='facility_staff',
            extra={
                'facility_id': escalation.facility_id,
                'facility_name': escalation.facility.name if escalation.facility else '',
                'status': escalation.status,
                'updated_by': actor_account.name,
            },
        ),
    )


def _notify_assigned_staff_status_update(escalation: FacilityEscalation, actor_account: FacilityAccount):
    if not escalation.assigned_staff:
        return
    if escalation.assigned_staff.id == actor_account.id:
        return

    assigned_user = _resolve_user_for_facility_account(escalation.assigned_staff)
    if not assigned_user:
        return

    status_text = escalation.status.replace('_', ' ')
    create_user_notification(
        user_id=assigned_user.id,
        event_type='facility:escalation_updated',
        title='Assigned Escalation Updated',
        message=f"Case for {escalation.mother_name} is now '{status_text}'.",
        url='/dashboard/facility',
        entity_type='facility_escalation',
        entity_id=escalation.id,
    )

    send_push(
        assigned_user.id,
        'Assigned Escalation Updated',
        f"Case for {escalation.mother_name} is now '{status_text}'.",
        build_push_data(
            event='facility:escalation_updated',
            url='/dashboard/facility',
            entity_type='facility_escalation',
            entity_id=escalation.id,
            role='facility_staff',
            extra={
                'facility_id': escalation.facility_id,
                'facility_name': escalation.facility.name if escalation.facility else '',
                'status': escalation.status,
                'updated_by': actor_account.name,
            },
        ),
    )


@bp.route('/facilities/claim/facilities', methods=['GET'])
def list_claimable_facilities():
    """
    Public discovery endpoint used by the facility admin claim flow.

    Query params:
      sub_county_id: required
      ward_id: required
      amenity: optional csv (default hospital,clinic)
      healthcare: optional csv (e.g. hospital,clinic,maternity)
      q: optional free-text search on name/address/city
      lat,lng: optional user coordinates for distance ranking
      limit: optional (default 40, max 80)
      include_claimed: optional (default false)
            relevance_profile: optional (maternal_referral|all), default maternal_referral
    """
    sub_county_id_raw = request.args.get('sub_county_id')
    ward_id_raw = request.args.get('ward_id')

    if not sub_county_id_raw or not ward_id_raw:
        return jsonify({'error': 'sub_county_id and ward_id are required'}), 400

    try:
        sub_county_id = int(sub_county_id_raw)
        ward_id = int(ward_id_raw)
    except (TypeError, ValueError):
        return jsonify({'error': 'sub_county_id and ward_id must be integers'}), 400

    sub_county = SubCounty.query.get(sub_county_id)
    if not sub_county:
        return jsonify({'error': 'Sub-county not found'}), 404

    ward = Ward.query.get(ward_id)
    if not ward:
        return jsonify({'error': 'Ward not found'}), 404

    if ward.sub_county_id != sub_county.id:
        return jsonify({'error': 'Ward does not belong to selected sub-county'}), 400

    amenity_values = _normalize_csv_param(request.args.get('amenity'), default_values=['hospital', 'clinic'])

    healthcare_values = _normalize_csv_param(request.args.get('healthcare'))
    relevance_profile = _resolve_relevance_profile(request.args.get('relevance_profile'), amenity_values)

    q = (request.args.get('q') or '').strip()
    include_claimed = str(request.args.get('include_claimed', 'false')).lower() == 'true'

    try:
        limit = min(max(int(request.args.get('limit', 40)), 1), 80)
    except (TypeError, ValueError):
        limit = 40

    lat = None
    lng = None
    if request.args.get('lat') is not None and request.args.get('lng') is not None:
        try:
            lat = float(request.args.get('lat'))
            lng = float(request.args.get('lng'))
        except (TypeError, ValueError):
            return jsonify({'error': 'lat and lng must be valid decimal numbers'}), 400

    base_query = (
        HealthFacility.query
        .filter(HealthFacility.name.isnot(None))
        .filter(func.length(func.trim(HealthFacility.name)) > 0)
        .filter(or_(HealthFacility.amenity.is_(None), HealthFacility.amenity != '*'))
        .filter(or_(HealthFacility.healthcare.is_(None), HealthFacility.healthcare != '*'))
    )
    if not include_claimed:
        base_query = base_query.filter(HealthFacility.facility_admin_id.is_(None))

    if amenity_values:
        base_query = base_query.filter(HealthFacility.amenity.in_(amenity_values))

    if healthcare_values:
        base_query = base_query.filter(
            or_(*[HealthFacility.healthcare.ilike(f'%{value}%') for value in healthcare_values])
        )

    base_query = _apply_relevance_profile(base_query, relevance_profile)

    if q:
        like = f'%{q}%'
        base_query = base_query.filter(
            or_(
                HealthFacility.name.ilike(like),
                HealthFacility.address.ilike(like),
                HealthFacility.city.ilike(like),
            )
        )

    ward_name = (ward.name or '').strip()
    sub_county_name = (sub_county.name or '').strip()

    facilities = base_query.filter(
        func.lower(func.coalesce(HealthFacility.subcounty_name, '')) == sub_county_name.lower(),
        func.lower(func.coalesce(HealthFacility.ward_name, '')) == ward_name.lower(),
    ).order_by(
        HealthFacility.verified.desc(),
        HealthFacility.name,
    ).limit(limit).all()

    serialized = []
    for facility in facilities:
        item = facility.to_dict()
        if lat is not None and lng is not None:
            distance_km = _distance_km_from_wkt(facility.geometry, lat, lng)
            if distance_km is not None:
                item['distance_km'] = distance_km
        serialized.append(item)

    if lat is not None and lng is not None:
        serialized.sort(key=lambda row: row.get('distance_km', 10_000))

    return jsonify({
        'sub_county': {'id': sub_county.id, 'name': sub_county.name},
        'ward': {'id': ward.id, 'name': ward.name},
        'matched_by': 'saved_admin_scope',
        'filter_profile': relevance_profile,
        'applied_filters': {
            'include_claimed': include_claimed,
            'amenity': amenity_values,
            'healthcare': healthcare_values,
            'q': q or None,
            'has_coordinates': bool(lat is not None and lng is not None),
        },
        'empty_state': (
            {
                'title': 'No unclaimed facilities found for this ward',
                'message': 'Try searching by facility name, or contact support if your facility should appear here.',
            }
            if not serialized else None
        ),
        'count': len(serialized),
        'facilities': serialized,
    }), 200


@bp.route('/facilities/admin/register', methods=['POST'])
def register_facility_admin():
    data = request.get_json() or {}

    phone_number = normalize_phone_number(data.get('phone_number', ''))
    first_name = (data.get('first_name') or '').strip()
    last_name = (data.get('last_name') or '').strip()
    email = (data.get('email') or '').strip().lower() or None
    pin = (data.get('pin') or '').strip()
    facility_id = data.get('facility_id')

    if not all([phone_number, first_name, last_name, pin, facility_id]):
        return jsonify({'error': 'phone_number, first_name, last_name, pin and facility_id are required'}), 400

    if not _is_normalized_kenyan_phone(phone_number):
        return jsonify({'error': 'Please enter phone number in 07xxxxxxxx format'}), 400

    if len(pin) < 4 or len(pin) > 8:
        return jsonify({'error': 'PIN must be between 4 and 8 characters'}), 400

    if FacilityAccount.query.filter_by(phone_number=phone_number).first():
        return jsonify({'error': 'Phone number already registered for a facility account'}), 409

    if email and FacilityAccount.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already registered for a facility account'}), 409

    facility = HealthFacility.query.get(facility_id)
    if not facility:
        return jsonify({'error': 'Facility not found'}), 404

    if facility.facility_admin_id:
        return jsonify({'error': 'Facility already claimed by another admin'}), 409

    now = datetime.now(timezone.utc)

    account = FacilityAccount(
        facility_id=facility.id,
        phone_number=phone_number,
        email=email,
        first_name=first_name,
        last_name=last_name,
        pin_hash=hash_pin(pin),
        role='admin',
        profile_completed=True,
        is_active=True,
        created_at=now,
        updated_at=now,
    )

    db.session.add(account)
    db.session.flush()

    facility.facility_admin_id = account.id
    facility.admin_verified_at = now
    facility.verified = True
    facility.verified_at = now

    db.session.add(
        FacilityStaff(
            facility_id=facility.id,
            account_id=account.id,
            role='admin',
            status='active',
            added_by_account_id=account.id,
            added_at=now,
        )
    )

    db.session.commit()

    _emit_facility_staff_update(facility.id)

    access_token = create_access_token(identity=_facility_identity(account.id))
    refresh_token = create_refresh_token(identity=_facility_identity(account.id))

    return jsonify({
        'message': 'Facility admin registered successfully',
        'access_token': access_token,
        'refresh_token': refresh_token,
        'facility': {
            'id': facility.id,
            'name': facility.name,
            'claimed': True,
        },
        'user': _auth_payload_for_account(account),
    }), 201


@bp.route('/facilities/staff/invite', methods=['POST'])
@require_facility_auth
def invite_facility_staff():
    current_account = request.current_facility_account
    data = request.get_json() or {}

    facility_id = data.get('facility_id')
    invited_role = (data.get('invited_role') or '').strip().lower()
    invitation_phone = normalize_phone_number(data.get('invitation_phone', '')) if data.get('invitation_phone') else None
    invitation_email = (data.get('invitation_email') or '').strip().lower() or None
    invited_first_name = (data.get('first_name') or '').strip()
    invited_last_name = (data.get('last_name') or '').strip()

    if not facility_id:
        return jsonify({'error': 'facility_id is required'}), 400
    if invited_role not in ASSIGNABLE_MEMBER_ROLES:
        return jsonify({'error': f'invited_role must be one of {sorted(ASSIGNABLE_MEMBER_ROLES)}'}), 400
    if not invitation_phone and not invitation_email:
        return jsonify({'error': 'invitation_phone or invitation_email is required'}), 400
    if invitation_phone and not _is_normalized_kenyan_phone(invitation_phone):
        return jsonify({'error': 'Please enter invitation_phone in 07xxxxxxxx format'}), 400

    facility = _admin_facility_for_account(current_account, facility_id)
    if not facility:
        return jsonify({'error': 'Only facility admin can invite staff'}), 403

    otp_code = generate_otp()
    now = datetime.now(timezone.utc)

    otp_token = OTPToken(
        phone_number=invitation_phone,
        email=invitation_email,
        otp_code=otp_code,
        purpose='facility_invitation',
        facility_id=facility.id,
        attempts=0,
        max_attempts=3,
        is_used=False,
        created_at=now,
        expires_at=now + timedelta(minutes=15),
    )

    db.session.add(otp_token)
    db.session.flush()

    invitation = FacilityInvitation(
        facility_id=facility.id,
        invitation_phone=invitation_phone,
        invitation_email=invitation_email,
        invited_role=invited_role,
        invited_by=current_account.id,
        status='pending',
        otp_id=otp_token.id,
        created_at=now,
    )

    db.session.add(invitation)
    db.session.flush()

    # Phase B: create/update membership row at invitation time and mark as pending verification.
    pending_membership = None
    if invitation_phone:
        pending_membership = FacilityStaff.query.filter(
            FacilityStaff.facility_id == facility.id,
            FacilityStaff.role == invited_role,
            FacilityStaff.account_id.is_(None),
            FacilityStaff.invitation_phone == invitation_phone,
            FacilityStaff.status == 'pending_verification',
        ).order_by(FacilityStaff.added_at.desc()).first()

    if not pending_membership:
        pending_membership = FacilityStaff(
            facility_id=facility.id,
            account_id=None,
            invitation_id=invitation.id,
            invitation_phone=invitation_phone,
            first_name=invited_first_name or None,
            last_name=invited_last_name or '',
            role=invited_role,
            status='pending_verification',
            is_verified=False,
            verified_at=None,
            added_by_account_id=current_account.id,
            added_at=now,
        )
        db.session.add(pending_membership)
    else:
        pending_membership.invitation_id = invitation.id
        if invited_first_name:
            pending_membership.first_name = invited_first_name
        if invited_last_name:
            pending_membership.last_name = invited_last_name
        pending_membership.role = invited_role
        pending_membership.status = 'pending_verification'
        pending_membership.is_verified = False
        pending_membership.verified_at = None

    db.session.commit()

    delivery_status = 'pending'
    delivery_method = 'email' if invitation_email and not invitation_phone else 'sms'

    if invitation_phone:
        success, delivery_message, delivery_method = send_otp(invitation_phone, otp_code)
        get_otp_service().log_otp_delivery(
            phone_number=invitation_phone,
            success=success,
            method=delivery_method,
            error=None if success else delivery_message,
        )
        delivery_status = 'sent' if success else 'failed'
    elif invitation_email:
        delivery_status = 'pending_email_integration'

    return jsonify({
        'message': 'Invitation created',
        'invitation_id': invitation.id,
        'staff_row_id': pending_membership.id,
        'facility_id': facility.id,
        'delivery_status': delivery_status,
        'delivery_method': delivery_method,
        'expires_at': invitation.expires_at.isoformat() if invitation.expires_at else None,
    }), 201


@bp.route('/facilities/staff/otp-request', methods=['POST'])
def request_facility_staff_otp():
    data = request.get_json() or {}

    phone_number = normalize_phone_number(data.get('phone_number', '')) if data.get('phone_number') else None
    email = (data.get('email') or '').strip().lower() or None

    if not phone_number and not email:
        return jsonify({'error': 'phone_number or email is required'}), 400

    if phone_number and not _is_normalized_kenyan_phone(phone_number):
        return jsonify({'error': 'Please enter phone number in 07xxxxxxxx format'}), 400

    now = datetime.now(timezone.utc)
    invitation_query = FacilityInvitation.query.filter_by(status='pending')

    if phone_number:
        invitation_query = invitation_query.filter_by(invitation_phone=phone_number)
    if email:
        invitation_query = invitation_query.filter_by(invitation_email=email)

    invitation = invitation_query.order_by(FacilityInvitation.created_at.desc()).first()
    if not invitation or not invitation.is_active():
        return jsonify({'error': 'No active invitation found for provided contact'}), 404

    otp_code = generate_otp()
    otp = OTPToken(
        phone_number=phone_number,
        email=email,
        otp_code=otp_code,
        purpose='facility_login',
        facility_id=invitation.facility_id,
        attempts=0,
        max_attempts=3,
        is_used=False,
        created_at=now,
        expires_at=now + timedelta(minutes=15),
    )
    db.session.add(otp)
    db.session.flush()

    invitation.otp_id = otp.id
    db.session.commit()

    delivery_status = 'pending'
    delivery_method = 'email' if email and not phone_number else 'sms'
    if phone_number:
        success, delivery_message, delivery_method = send_otp(phone_number, otp_code)
        get_otp_service().log_otp_delivery(
            phone_number=phone_number,
            success=success,
            method=delivery_method,
            error=None if success else delivery_message,
        )
        delivery_status = 'sent' if success else 'failed'
    elif email:
        delivery_status = 'pending_email_integration'

    return jsonify({
        'message': 'OTP issued for facility staff login',
        'delivery_status': delivery_status,
        'delivery_method': delivery_method,
        'expires_at': otp.expires_at.isoformat() if otp.expires_at else None,
    }), 200


@bp.route('/facilities/staff/otp-login', methods=['POST'])
def facility_staff_otp_login():
    data = request.get_json() or {}

    otp_code = (data.get('otp_code') or '').strip()
    phone_number = normalize_phone_number(data.get('phone_number', '')) if data.get('phone_number') else None
    email = (data.get('email') or '').strip().lower() or None

    if not otp_code or (not phone_number and not email):
        return jsonify({'error': 'otp_code and phone_number/email are required'}), 400

    if phone_number and not _is_normalized_kenyan_phone(phone_number):
        return jsonify({'error': 'Please enter phone number in 07xxxxxxxx format'}), 400

    query = OTPToken.query.filter_by(otp_code=otp_code, is_used=False).order_by(OTPToken.created_at.desc())
    if phone_number:
        query = query.filter_by(phone_number=phone_number)
    if email:
        query = query.filter_by(email=email)

    otp = query.first()
    if not otp:
        return jsonify({'error': 'Invalid OTP'}), 400

    if not otp.is_valid():
        otp.attempts += 1
        db.session.commit()
        return jsonify({'error': 'OTP expired or max attempts reached'}), 400

    invitation_query = FacilityInvitation.query.filter_by(otp_id=otp.id)
    if phone_number:
        invitation_query = invitation_query.filter_by(invitation_phone=phone_number)
    if email:
        invitation_query = invitation_query.filter_by(invitation_email=email)

    invitation = invitation_query.order_by(FacilityInvitation.created_at.desc()).first()
    if not invitation:
        otp.attempts += 1
        db.session.commit()
        return jsonify({'error': 'Invitation not found for provided OTP'}), 404

    if not invitation.is_active():
        invitation.status = 'expired'
        db.session.commit()
        return jsonify({'error': 'Invitation expired'}), 400

    account = _find_facility_account_by_contact(phone_number=phone_number, email=email)

    pending_membership = FacilityStaff.query.filter(
        FacilityStaff.invitation_id == invitation.id,
        FacilityStaff.facility_id == invitation.facility_id,
        FacilityStaff.status == 'pending_verification',
    ).order_by(FacilityStaff.added_at.desc()).first()

    if not pending_membership and phone_number:
        pending_membership = FacilityStaff.query.filter(
            FacilityStaff.facility_id == invitation.facility_id,
            FacilityStaff.invitation_phone == phone_number,
            FacilityStaff.role == invitation.invited_role,
            FacilityStaff.status == 'pending_verification',
        ).order_by(FacilityStaff.added_at.desc()).first()

    now = datetime.now(timezone.utc)
    created_new_account = False

    if not account:
        account_first_name = (
            pending_membership.first_name
            if pending_membership and pending_membership.first_name
            else ''
        )
        account_last_name = (
            pending_membership.last_name
            if pending_membership and pending_membership.last_name
            else ''
        )

        account = FacilityAccount(
            facility_id=invitation.facility_id,
            phone_number=phone_number,
            email=email,
            first_name=account_first_name,
            last_name=account_last_name,
            pin_hash=None,
            role=invitation.invited_role,
            profile_completed=False,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.session.add(account)
        db.session.flush()
        created_new_account = True

    membership = pending_membership
    if not membership:
        membership = FacilityStaff.query.filter_by(facility_id=invitation.facility_id, account_id=account.id).first()

    if not membership:
        membership = FacilityStaff(
            facility_id=invitation.facility_id,
            account_id=account.id,
            invitation_id=invitation.id,
            invitation_phone=phone_number,
            first_name=account.first_name,
            last_name=account.last_name,
            role=invitation.invited_role,
            status='active',
            is_verified=True,
            verified_at=now,
            added_by_account_id=invitation.invited_by,
            added_at=now,
        )
        db.session.add(membership)
    else:
        membership.account_id = account.id
        membership.invitation_id = invitation.id
        membership.invitation_phone = phone_number or membership.invitation_phone
        membership.first_name = membership.first_name or account.first_name
        membership.last_name = membership.last_name or account.last_name
        membership.role = invitation.invited_role
        membership.status = 'active'
        membership.is_verified = True
        membership.verified_at = now

    linked_user = _resolve_user_for_facility_account(account)
    if linked_user and not membership.user_id:
        membership.user_id = linked_user.id

    account.facility_id = invitation.facility_id
    account.role = invitation.invited_role
    if not account.first_name:
        account.first_name = membership.first_name or ''
    if not account.last_name:
        account.last_name = membership.last_name or ''
    account.updated_at = now

    otp.is_used = True
    otp.used_at = now
    invitation.status = 'accepted'
    invitation.accepted_at = now

    db.session.commit()

    _emit_facility_staff_update(invitation.facility_id)

    access_token = create_access_token(identity=_facility_identity(account.id))
    refresh_token = create_refresh_token(identity=_facility_identity(account.id))

    return jsonify({
        'message': 'Facility staff login successful',
        'access_token': access_token,
        'refresh_token': refresh_token,
        'requires_profile_completion': not bool(account.profile_completed),
        'created_new_user': created_new_account,
        'membership': membership.to_dict(),
        'user': _auth_payload_for_account(account),
    }), 200


@bp.route('/facilities/staff/profile-complete', methods=['POST'])
@require_facility_auth
def complete_facility_staff_profile():
    current_account = request.current_facility_account
    data = request.get_json() or {}

    first_name = (data.get('first_name') or '').strip()
    last_name = (data.get('last_name') or '').strip()
    email = (data.get('email') or '').strip().lower() or None
    requested_phone = (data.get('updated_phone_number') or data.get('phone_number') or '').strip()
    phone_number = normalize_phone_number(requested_phone) if requested_phone else None
    pin = (data.get('pin') or '').strip()
    specialty = (data.get('specialty') or '').strip() or None

    if not first_name or not last_name:
        return jsonify({'error': 'first_name and last_name are required'}), 400

    if phone_number is not None and not _is_normalized_kenyan_phone(phone_number):
        return jsonify({'error': 'Please enter phone number in 07xxxxxxxx format'}), 400

    membership = _active_membership(current_account.id)
    if not membership:
        return jsonify({'error': 'Facility staff membership not found'}), 403

    invited_phone_number = membership.invitation_phone or current_account.phone_number

    current_account.first_name = first_name
    current_account.last_name = last_name

    if email is not None:
        existing_email_owner = FacilityAccount.query.filter(
            FacilityAccount.email == email,
            FacilityAccount.id != current_account.id,
        ).first()
        if existing_email_owner:
            return jsonify({'error': 'Email already in use by another facility account'}), 409
        current_account.email = email

    if phone_number is not None:
        existing_phone_owner = FacilityAccount.query.filter(
            FacilityAccount.phone_number == phone_number,
            FacilityAccount.id != current_account.id,
        ).first()
        if existing_phone_owner:
            return jsonify({'error': 'Phone number already in use by another facility account'}), 409

        # Phone update is optional. When supplied, latest value becomes the
        # primary login/OTP number across account + membership + invitation.
        current_account.phone_number = phone_number
        membership.invitation_phone = phone_number

        invitation_matchers = []
        if membership.invitation_id:
            invitation_matchers.append(FacilityInvitation.id == membership.invitation_id)
        if invited_phone_number:
            invitation_matchers.append(FacilityInvitation.invitation_phone == invited_phone_number)
        if current_account.email:
            invitation_matchers.append(FacilityInvitation.invitation_email == current_account.email)

        if invitation_matchers:
            latest_invitation = FacilityInvitation.query.filter(
                FacilityInvitation.facility_id == membership.facility_id,
                or_(*invitation_matchers),
            ).order_by(FacilityInvitation.created_at.desc()).first()
            if latest_invitation:
                latest_invitation.invitation_phone = phone_number

    if pin:
        if len(pin) < 4 or len(pin) > 8:
            return jsonify({'error': 'PIN must be between 4 and 8 characters'}), 400
        current_account.pin_hash = hash_pin(pin)

    # Keep compatibility with current client while allowing richer profile completion payloads.
    current_account.profile_completed = True
    current_account.updated_at = datetime.now(timezone.utc)

    if specialty:
        membership.specialty = specialty

    db.session.commit()

    return jsonify({
        'message': 'Profile completed successfully',
        'user': _auth_payload_for_account(current_account),
        'membership': membership.to_dict(),
        'pin_set': bool(current_account.pin_hash),
        'invited_phone_number': current_account.phone_number,
    }), 200


@bp.route('/facilities/admin/login', methods=['POST'])
@bp.route('/facilities/admin/pin-login', methods=['POST'])
def facility_admin_login_with_pin():
    """Dedicated facility admin login endpoint (PIN-based)."""
    data = request.get_json() or {}
    phone_number = normalize_phone_number(data.get('phone_number', '')) if data.get('phone_number') else None
    email = (data.get('email') or '').strip().lower() or None
    pin = (data.get('pin') or '').strip()
    otp_code = (data.get('otp_code') or '').strip()

    if not pin or (not phone_number and not email):
        return jsonify({'error': 'pin and phone_number/email are required'}), 400

    if phone_number and not _is_normalized_kenyan_phone(phone_number):
        return jsonify({'error': 'Please enter phone number in 07xxxxxxxx format'}), 400

    account = _find_facility_account_by_contact(phone_number=phone_number, email=email)
    if not account or account.role != 'admin':
        return jsonify({'error': 'Admin account not found'}), 404
    if not account.is_active:
        return jsonify({'error': 'Account is inactive'}), 403
    if not account.pin_hash:
        return jsonify({'error': 'PIN is not set for this account'}), 400
    if not verify_pin(pin, account.pin_hash):
        return jsonify({'error': 'Invalid credentials'}), 401

    otp_phone = account.phone_number or phone_number
    now = datetime.now(timezone.utc)

    if not otp_code:
        if not otp_phone or not _is_normalized_kenyan_phone(otp_phone):
            return jsonify({'error': 'A valid support line is required for OTP login verification'}), 400

        stale_tokens = OTPToken.query.filter_by(
            phone_number=otp_phone,
            purpose='facility_pin_login',
            is_used=False,
        ).all()

        for token in stale_tokens:
            token.is_used = True
            token.used_at = now

        login_otp_code = generate_otp()
        login_otp = OTPToken(
            phone_number=otp_phone,
            email=account.email,
            otp_code=login_otp_code,
            purpose='facility_pin_login',
            facility_id=account.facility_id,
            attempts=0,
            max_attempts=5,
            is_used=False,
            created_at=now,
            expires_at=now + timedelta(minutes=10),
        )
        db.session.add(login_otp)
        db.session.commit()

        success, delivery_msg, delivery_method = send_otp(otp_phone, login_otp_code)
        get_otp_service().log_otp_delivery(
            phone_number=otp_phone,
            success=success,
            method=delivery_method,
            error=None if success else delivery_msg,
        )

        return jsonify({
            'message': 'OTP sent. Enter the code to complete login.',
            'requires_otp': True,
            'expires_in': '10 minutes',
            'otp_delivery_status': 'sent' if success else 'pending_retry',
        }), 200

    if not otp_phone or not _is_normalized_kenyan_phone(otp_phone):
        return jsonify({'error': 'A valid support line is required for OTP login verification'}), 400

    login_otp = OTPToken.query.filter_by(
        phone_number=otp_phone,
        purpose='facility_pin_login',
        is_used=False,
    ).order_by(OTPToken.created_at.desc()).first()

    if not login_otp:
        return jsonify({'error': 'No active login OTP found. Request a new code.'}), 400

    if not login_otp.is_valid():
        login_otp.attempts += 1
        db.session.commit()
        return jsonify({'error': 'Login OTP expired or max attempts reached. Request a new code.'}), 400

    if login_otp.otp_code != otp_code:
        login_otp.attempts += 1
        db.session.commit()
        return jsonify({'error': 'Invalid OTP. Please try again.'}), 401

    login_otp.is_used = True
    login_otp.used_at = now

    access_token = create_access_token(identity=_facility_identity(account.id))
    refresh_token = create_refresh_token(identity=_facility_identity(account.id))

    account.updated_at = now
    db.session.commit()

    return jsonify({
        'message': 'Facility admin login successful',
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': _auth_payload_for_account(account),
    }), 200


@bp.route('/facilities/staff/pin-login', methods=['POST'])
@bp.route('/facilities/staff/login', methods=['POST'])
def facility_staff_pin_login():
    """PIN login for facility staff after invitation/profile completion."""
    data = request.get_json() or {}
    phone_number = normalize_phone_number(data.get('phone_number', '')) if data.get('phone_number') else None
    email = (data.get('email') or '').strip().lower() or None
    pin = (data.get('pin') or '').strip()
    otp_code = (data.get('otp_code') or '').strip()

    if not pin or (not phone_number and not email):
        return jsonify({'error': 'pin and phone_number/email are required'}), 400

    if phone_number and not _is_normalized_kenyan_phone(phone_number):
        return jsonify({'error': 'Please enter phone number in 07xxxxxxxx format'}), 400

    account = _find_facility_account_by_contact(phone_number=phone_number, email=email)
    if not account:
        return jsonify({'error': 'Facility account not found'}), 404
    if not account.is_active:
        return jsonify({'error': 'Account is inactive'}), 403
    if account.role not in ALLOWED_STAFF_ROLES:
        return jsonify({'error': 'Unsupported facility account role'}), 403
    if not account.pin_hash:
        return jsonify({'error': 'PIN is not set for this account'}), 400
    if not verify_pin(pin, account.pin_hash):
        return jsonify({'error': 'Invalid credentials'}), 401

    otp_phone = account.phone_number or phone_number
    now = datetime.now(timezone.utc)

    if not otp_code:
        if not otp_phone or not _is_normalized_kenyan_phone(otp_phone):
            return jsonify({'error': 'A valid support line is required for OTP login verification'}), 400

        stale_tokens = OTPToken.query.filter_by(
            phone_number=otp_phone,
            purpose='facility_pin_login',
            is_used=False,
        ).all()

        for token in stale_tokens:
            token.is_used = True
            token.used_at = now

        login_otp_code = generate_otp()
        login_otp = OTPToken(
            phone_number=otp_phone,
            email=account.email,
            otp_code=login_otp_code,
            purpose='facility_pin_login',
            facility_id=account.facility_id,
            attempts=0,
            max_attempts=5,
            is_used=False,
            created_at=now,
            expires_at=now + timedelta(minutes=10),
        )
        db.session.add(login_otp)
        db.session.commit()

        success, delivery_msg, delivery_method = send_otp(otp_phone, login_otp_code)
        get_otp_service().log_otp_delivery(
            phone_number=otp_phone,
            success=success,
            method=delivery_method,
            error=None if success else delivery_msg,
        )

        return jsonify({
            'message': 'OTP sent. Enter the code to complete login.',
            'requires_otp': True,
            'expires_in': '10 minutes',
            'otp_delivery_status': 'sent' if success else 'pending_retry',
        }), 200

    if not otp_phone or not _is_normalized_kenyan_phone(otp_phone):
        return jsonify({'error': 'A valid support line is required for OTP login verification'}), 400

    login_otp = OTPToken.query.filter_by(
        phone_number=otp_phone,
        purpose='facility_pin_login',
        is_used=False,
    ).order_by(OTPToken.created_at.desc()).first()

    if not login_otp:
        return jsonify({'error': 'No active login OTP found. Request a new code.'}), 400

    if not login_otp.is_valid():
        login_otp.attempts += 1
        db.session.commit()
        return jsonify({'error': 'Login OTP expired or max attempts reached. Request a new code.'}), 400

    if login_otp.otp_code != otp_code:
        login_otp.attempts += 1
        db.session.commit()
        return jsonify({'error': 'Invalid OTP. Please try again.'}), 401

    login_otp.is_used = True
    login_otp.used_at = now

    membership = _active_membership(account.id)
    if not membership:
        return jsonify({'error': 'Active facility membership not found'}), 403

    access_token = create_access_token(identity=_facility_identity(account.id))
    refresh_token = create_refresh_token(identity=_facility_identity(account.id))

    account.updated_at = now
    db.session.commit()

    return jsonify({
        'message': 'Facility staff login successful',
        'access_token': access_token,
        'refresh_token': refresh_token,
        'requires_profile_completion': not bool(account.profile_completed),
        'user': _auth_payload_for_account(account),
        'membership': membership.to_dict(),
    }), 200


@bp.route('/facilities/auth/me', methods=['GET'])
@require_facility_auth
def get_facility_auth_me():
    """Stable auth context endpoint for facility dashboard bootstrap."""
    current_account = request.current_facility_account
    membership = _active_membership(current_account.id)
    admin_facility = _admin_facility_for_account(current_account)

    return jsonify({
        'user': _auth_payload_for_account(current_account),
        'membership': membership.to_dict() if membership else None,
        'is_admin': bool(admin_facility),
        'facility_id': admin_facility.id if admin_facility else (membership.facility_id if membership else current_account.facility_id),
    }), 200


@bp.route('/facilities/<int:facility_id>/nurse-compat/context', methods=['GET'])
@require_facility_auth
def get_nurse_compat_context(facility_id):
    current_account = request.current_facility_account
    resolved = _ensure_nurse_compat_scope(current_account, facility_id)
    if len(resolved) != 4:
        return resolved

    resolved_facility_id, is_admin, membership, role = resolved
    facility = HealthFacility.query.get(resolved_facility_id)
    if not facility:
        return jsonify({'error': 'Facility not found'}), 404

    return jsonify({
        'mode': 'facility_nurse_compat',
        'facility_id': resolved_facility_id,
        'is_admin': is_admin,
        'membership': membership.to_dict() if membership else None,
        'profile': {
            'id': current_account.id,
            'nurse_name': current_account.name,
            'role': role,
            'location': _format_legacy_nurse_location(facility),
        },
        'capabilities': {
            'can_assign_escalations': bool(is_admin),
            'can_update_escalation_status': bool(is_admin),
            'can_create_appointments': True,
            'can_edit_appointments': True,
            'supports_soft_hide': False,
        },
    }), 200


@bp.route('/facilities/<int:facility_id>/nurse-compat/escalations', methods=['GET'])
@require_facility_auth
def list_nurse_compat_escalations(facility_id):
    current_account = request.current_facility_account
    resolved = _ensure_nurse_compat_scope(current_account, facility_id)
    if len(resolved) != 4:
        return resolved

    resolved_facility_id, is_admin, _membership, _role = resolved
    status_filter = (request.args.get('status') or '').strip().lower()
    priority_filter = (request.args.get('priority') or '').strip().lower()
    assigned_only = str(request.args.get('assigned_to_me', 'false')).lower() in {'1', 'true', 'yes'}
    hidden_only = str(request.args.get('hidden_only', 'false')).lower() in {'1', 'true', 'yes'}
    include_hidden = str(request.args.get('include_hidden', 'false')).lower() in {'1', 'true', 'yes'}

    query = FacilityEscalation.query.filter_by(facility_id=resolved_facility_id)

    mapped_status = NURSE_COMPAT_TO_FACILITY_STATUS.get(status_filter)
    if mapped_status:
        query = query.filter(FacilityEscalation.status == mapped_status)
    if priority_filter:
        query = query.filter(FacilityEscalation.priority == priority_filter)
    if assigned_only and not is_admin:
        query = query.filter(FacilityEscalation.assigned_staff_account_id == current_account.id)

    rows = query.order_by(FacilityEscalation.created_at.desc()).all()
    if hidden_only:
        rows = [row for row in rows if _nurse_compat_escalation_is_hidden(row)]
    elif not include_hidden:
        rows = [row for row in rows if not _nurse_compat_escalation_is_hidden(row)]

    return jsonify({
        'facility_id': resolved_facility_id,
        'total': len(rows),
        'escalations': [_serialize_nurse_compat_escalation(row) for row in rows],
    }), 200


@bp.route('/facilities/<int:facility_id>/nurse-compat/escalations/<int:escalation_id>', methods=['GET'])
@require_facility_auth
def get_nurse_compat_escalation(facility_id, escalation_id):
    current_account = request.current_facility_account
    resolved = _ensure_nurse_compat_scope(current_account, facility_id)
    if len(resolved) != 4:
        return resolved

    resolved_facility_id, _is_admin, _membership, _role = resolved
    row = FacilityEscalation.query.get(escalation_id)
    if not row or row.facility_id != resolved_facility_id:
        return jsonify({'error': 'Escalation not found'}), 404

    return jsonify(_serialize_nurse_compat_escalation(row)), 200


@bp.route('/facilities/<int:facility_id>/nurse-compat/escalations/<int:escalation_id>', methods=['PATCH'])
@require_facility_auth
def update_nurse_compat_escalation(facility_id, escalation_id):
    current_account = request.current_facility_account
    resolved = _ensure_nurse_compat_scope(current_account, facility_id)
    if len(resolved) != 4:
        return resolved

    resolved_facility_id, is_admin, _membership, _role = resolved
    row = FacilityEscalation.query.get(escalation_id)
    if not row or row.facility_id != resolved_facility_id:
        return jsonify({'error': 'Escalation not found'}), 404

    data = request.get_json() or {}

    if 'notes' in data:
        row.notes = (data.get('notes') or '').strip() or None

    if 'priority' in data:
        if not is_admin:
            return jsonify({'error': 'Only facility admin can update escalation priority'}), 403
        incoming_priority = (data.get('priority') or '').strip().lower()
        if incoming_priority not in {'low', 'medium', 'high', 'critical'}:
            return jsonify({'error': 'priority must be one of low, medium, high, critical'}), 400
        row.priority = incoming_priority

    if 'issue_type' in data and is_admin:
        row.issue_type = (data.get('issue_type') or '').strip() or None
    elif 'issue_type' in data and not is_admin:
        return jsonify({'error': 'Only facility admin can update issue_type'}), 403

    if 'case_description' in data:
        if not is_admin:
            return jsonify({'error': 'Only facility admin can update case_description'}), 403
        case_description = (data.get('case_description') or '').strip()
        if not case_description:
            return jsonify({'error': 'case_description cannot be empty'}), 400
        row.case_description = case_description

    row.updated_by_account_id = current_account.id
    row.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    _emit_facility_escalation('facility:escalation_updated', row)

    return jsonify({
        'message': 'Escalation updated',
        'escalation': _serialize_nurse_compat_escalation(row),
    }), 200


@bp.route('/facilities/<int:facility_id>/nurse-compat/escalations/<int:escalation_id>/delete', methods=['POST'])
@require_facility_auth
def hide_nurse_compat_escalation(facility_id, escalation_id):
    current_account = request.current_facility_account
    resolved = _ensure_nurse_compat_scope(current_account, facility_id)
    if len(resolved) != 4:
        return resolved

    resolved_facility_id, _is_admin, _membership, _role = resolved
    row = FacilityEscalation.query.get(escalation_id)
    if not row or row.facility_id != resolved_facility_id:
        return jsonify({'error': 'Escalation not found'}), 404

    row.notes = _nurse_compat_mark_hidden(row.notes)
    row.updated_by_account_id = current_account.id
    row.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    _emit_facility_escalation('facility:escalation_updated', row)
    return jsonify({'message': 'Escalation hidden', 'escalation_id': row.id}), 200


@bp.route('/facilities/<int:facility_id>/nurse-compat/escalations/<int:escalation_id>/delete', methods=['DELETE'])
@require_facility_auth
def restore_hidden_nurse_compat_escalation(facility_id, escalation_id):
    current_account = request.current_facility_account
    resolved = _ensure_nurse_compat_scope(current_account, facility_id)
    if len(resolved) != 4:
        return resolved

    resolved_facility_id, _is_admin, _membership, _role = resolved
    row = FacilityEscalation.query.get(escalation_id)
    if not row or row.facility_id != resolved_facility_id:
        return jsonify({'error': 'Escalation not found'}), 404

    row.notes = _nurse_compat_unmark_hidden(row.notes)
    row.updated_by_account_id = current_account.id
    row.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    _emit_facility_escalation('facility:escalation_updated', row)
    return jsonify({'message': 'Escalation restored', 'escalation_id': row.id}), 200


@bp.route('/facilities/<int:facility_id>/nurse-compat/escalations/<int:escalation_id>/status', methods=['PATCH'])
@require_facility_auth
def update_nurse_compat_escalation_status(facility_id, escalation_id):
    current_account = request.current_facility_account
    resolved = _ensure_nurse_compat_scope(current_account, facility_id)
    if len(resolved) != 4:
        return resolved

    resolved_facility_id, is_admin, _membership, _role = resolved
    if not is_admin:
        return jsonify({'error': 'Only facility admin can update escalation status'}), 403

    row = FacilityEscalation.query.get(escalation_id)
    if not row or row.facility_id != resolved_facility_id:
        return jsonify({'error': 'Escalation not found'}), 404

    data = request.get_json() or {}
    requested_status = (data.get('status') or '').strip().lower()
    mapped_status = NURSE_COMPAT_TO_FACILITY_STATUS.get(requested_status)
    if mapped_status not in FACILITY_ESCALATION_STATUSES:
        return jsonify({'error': 'status must be one of pending, in_progress, resolved, rejected'}), 400

    row.status = mapped_status
    row.updated_by_account_id = current_account.id
    row.updated_at = datetime.now(timezone.utc)
    row.checked_out_at = datetime.now(timezone.utc) if mapped_status == 'checked_out' else None
    if 'notes' in data:
        row.notes = (data.get('notes') or '').strip() or row.notes

    db.session.commit()

    _emit_facility_escalation('facility:escalation_updated', row)
    _notify_facility_escalation_status_change(row)
    _notify_facility_admin_status_update(row, current_account)
    _notify_assigned_staff_status_update(row, current_account)

    return jsonify({
        'message': f"Escalation status updated to {requested_status}",
        'escalation': _serialize_nurse_compat_escalation(row),
    }), 200


@bp.route('/facilities/<int:facility_id>/nurse-compat/appointments', methods=['GET'])
@require_facility_auth
def list_nurse_compat_appointments(facility_id):
    current_account = request.current_facility_account
    resolved = _ensure_nurse_compat_scope(current_account, facility_id)
    if len(resolved) != 4:
        return resolved

    resolved_facility_id, is_admin, _membership, _role = resolved
    status_filter = (request.args.get('status') or '').strip().lower()
    hidden_only = str(request.args.get('hidden_only', 'false')).lower() in {'1', 'true', 'yes'}
    include_hidden = str(request.args.get('include_hidden', 'false')).lower() in {'1', 'true', 'yes'}

    query = FacilityAppointment.query.filter_by(facility_id=resolved_facility_id)
    if status_filter:
        query = query.filter(FacilityAppointment.status == status_filter)
    elif hidden_only:
        query = query.filter(FacilityAppointment.status == 'canceled')
    elif not include_hidden:
        query = query.filter(FacilityAppointment.status != 'canceled')
    if not is_admin:
        query = query.filter(
            or_(
                FacilityAppointment.assigned_staff_account_id == current_account.id,
                FacilityAppointment.created_by_account_id == current_account.id,
            )
        )

    rows = query.order_by(FacilityAppointment.scheduled_time.asc()).all()
    return jsonify({
        'facility_id': resolved_facility_id,
        'total': len(rows),
        'appointments': [_serialize_nurse_compat_appointment(row) for row in rows],
    }), 200


@bp.route('/facilities/<int:facility_id>/nurse-compat/appointments/<int:appointment_id>', methods=['PATCH'])
@require_facility_auth
def update_nurse_compat_appointment(facility_id, appointment_id):
    current_account = request.current_facility_account
    resolved = _ensure_nurse_compat_scope(current_account, facility_id)
    if len(resolved) != 4:
        return resolved

    resolved_facility_id, is_admin, _membership, _role = resolved
    appointment = FacilityAppointment.query.get(appointment_id)
    if not appointment or appointment.facility_id != resolved_facility_id:
        return jsonify({'error': 'Appointment not found'}), 404

    if not is_admin:
        allowed_actor = (
            appointment.assigned_staff_account_id == current_account.id
            or appointment.created_by_account_id == current_account.id
        )
        if not allowed_actor:
            return jsonify({'error': 'Only the assigned or creator staff member can update this appointment'}), 403

    data = request.get_json() or {}
    previous_scheduled_time = appointment.scheduled_time.isoformat() if appointment.scheduled_time else None
    if 'scheduled_time' in data:
        parsed = _parse_iso_datetime(data.get('scheduled_time'))
        if not parsed:
            return jsonify({'error': 'valid scheduled_time is required'}), 400
        minimum_time_error = _validate_minimum_schedule_time(parsed)
        if minimum_time_error:
            return minimum_time_error
        appointment.scheduled_time = parsed

    if 'appointment_type' in data:
        appointment.appointment_type = (data.get('appointment_type') or '').strip() or None

    if 'notes' in data:
        appointment.notes = (data.get('notes') or '').strip() or None

    appointment.updated_at = datetime.now(timezone.utc)
    if 'scheduled_time' in data and appointment.scheduled_time and appointment.scheduled_time.isoformat() != previous_scheduled_time:
        _apply_facility_ticket_state_for_status(appointment, 'scheduled')
        _log_facility_ticket_event(
            appointment,
            'rescheduled',
            actor_account_id=current_account.id,
            actor_role=current_account.role,
            metadata={
                'previous_scheduled_time': previous_scheduled_time,
                'new_scheduled_time': appointment.scheduled_time.isoformat(),
            }
        )
    db.session.commit()

    _emit_facility_appointment('facility:appointment_updated', resolved_facility_id, appointment)
    _notify_mother_facility_appointment(appointment, 'facility:appointment_updated')
    _notify_assigned_facility_staff_for_appointment(appointment)

    return jsonify({
        'message': 'Appointment updated',
        'appointment': _serialize_nurse_compat_appointment(appointment),
    }), 200


@bp.route('/facilities/<int:facility_id>/nurse-compat/appointments', methods=['POST'])
@require_facility_auth
def create_nurse_compat_appointment(facility_id):
    current_account = request.current_facility_account
    resolved = _ensure_nurse_compat_scope(current_account, facility_id)
    if len(resolved) != 4:
        return resolved

    resolved_facility_id, _is_admin, _membership, _role = resolved
    data = request.get_json() or {}

    scheduled_time = _parse_iso_datetime(data.get('scheduled_time'))
    if not scheduled_time:
        return jsonify({'error': 'valid scheduled_time is required'}), 400
    minimum_time_error = _validate_minimum_schedule_time(scheduled_time)
    if minimum_time_error:
        return minimum_time_error

    mother_id, mother_name, mother_resolution_error = _resolve_mother_for_appointment(
        mother_id=data.get('mother_id'),
        mother_phone_number=data.get('mother_phone_number'),
    )
    if mother_resolution_error:
        return mother_resolution_error

    appointment = FacilityAppointment(
        facility_id=resolved_facility_id,
        mother_id=mother_id,
        mother_name=mother_name,
        scheduled_time=scheduled_time,
        appointment_type=(data.get('appointment_type') or '').strip() or None,
        status=(data.get('status') or 'scheduled').strip().lower(),
        created_by_account_id=current_account.id,
        notes=(data.get('notes') or '').strip() or None,
        ticket_code=_create_facility_appointment_ticket_code(),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    if appointment.status not in {'scheduled', 'assigned', 'completed', 'canceled'}:
        return jsonify({'error': 'status must be one of scheduled, assigned, completed, canceled'}), 400
    _apply_facility_ticket_state_for_status(
        appointment,
        appointment.status,
        actor_account_id=current_account.id if appointment.status == 'completed' else None,
    )

    db.session.add(appointment)
    db.session.flush()
    _log_facility_ticket_event(
        appointment,
        'generated',
        actor_account_id=current_account.id,
        actor_role=current_account.role,
        metadata={'scheduled_time': appointment.scheduled_time.isoformat() if appointment.scheduled_time else None}
    )
    db.session.commit()

    _emit_facility_appointment('facility:appointment_created', resolved_facility_id, appointment)
    _notify_mother_facility_appointment(appointment, 'facility:appointment_created')
    _notify_facility_admin_for_new_appointment(appointment)

    return jsonify({
        'message': 'Appointment created',
        'appointment': _serialize_nurse_compat_appointment(appointment),
    }), 201


@bp.route('/facilities/<int:facility_id>/nurse-compat/appointments/<int:appointment_id>/status', methods=['PATCH'])
@require_facility_auth
def update_nurse_compat_appointment_status(facility_id, appointment_id):
    current_account = request.current_facility_account
    resolved = _ensure_nurse_compat_scope(current_account, facility_id)
    if len(resolved) != 4:
        return resolved

    resolved_facility_id, is_admin, _membership, _role = resolved
    appointment = FacilityAppointment.query.get(appointment_id)
    if not appointment or appointment.facility_id != resolved_facility_id:
        return jsonify({'error': 'Appointment not found'}), 404

    data = request.get_json() or {}
    new_status = (data.get('status') or '').strip().lower()
    if new_status not in {'scheduled', 'assigned', 'completed', 'canceled'}:
        return jsonify({'error': 'status must be one of scheduled, assigned, completed, canceled'}), 400

    if not is_admin and new_status in {'scheduled', 'assigned'}:
        return jsonify({'error': 'Only facility admin can set scheduled/assigned status manually'}), 403

    if not is_admin:
        allowed_actor = (
            appointment.assigned_staff_account_id == current_account.id
            or appointment.created_by_account_id == current_account.id
        )
        if not allowed_actor:
            return jsonify({'error': 'Only the assigned or creator staff member can update this appointment'}), 403

    previous_status = appointment.status
    appointment.status = new_status
    _apply_facility_ticket_state_for_status(
        appointment,
        new_status,
        actor_account_id=current_account.id if new_status == 'completed' else None,
        validation_method=appointment.validation_method,
    )
    appointment.updated_at = datetime.now(timezone.utc)
    if 'notes' in data:
        appointment.notes = (data.get('notes') or '').strip() or appointment.notes
    if previous_status != new_status:
        event_type = 'canceled' if new_status == 'canceled' else 'validated' if new_status == 'completed' else 'rescheduled' if new_status == 'scheduled' else None
        if event_type:
            _log_facility_ticket_event(
                appointment,
                event_type,
                actor_account_id=current_account.id,
                actor_role=current_account.role,
                metadata={'previous_status': previous_status, 'new_status': new_status}
            )
    db.session.commit()

    _emit_facility_appointment('facility:appointment_updated', resolved_facility_id, appointment)
    _notify_mother_facility_appointment(appointment, 'facility:appointment_updated')
    _notify_assigned_facility_staff_for_appointment(appointment)

    return jsonify({
        'message': f'Appointment status updated to {new_status}',
        'appointment': _serialize_nurse_compat_appointment(appointment),
    }), 200


@bp.route('/facilities/<int:facility_id>/nurse-compat/appointments/<int:appointment_id>', methods=['DELETE'])
@require_facility_auth
def delete_nurse_compat_appointment(facility_id, appointment_id):
    current_account = request.current_facility_account
    resolved = _ensure_nurse_compat_scope(current_account, facility_id)
    if len(resolved) != 4:
        return resolved

    resolved_facility_id, is_admin, _membership, _role = resolved
    appointment = FacilityAppointment.query.get(appointment_id)
    if not appointment or appointment.facility_id != resolved_facility_id:
        return jsonify({'error': 'Appointment not found'}), 404

    if not is_admin:
        allowed_actor = (
            appointment.assigned_staff_account_id == current_account.id
            or appointment.created_by_account_id == current_account.id
        )
        if not allowed_actor:
            return jsonify({'error': 'Only the assigned or creator staff member can delete this appointment'}), 403

    previous_status = appointment.status
    appointment.status = 'canceled'
    _apply_facility_ticket_state_for_status(appointment, 'canceled')
    appointment.updated_at = datetime.now(timezone.utc)
    _log_facility_ticket_event(
        appointment,
        'canceled',
        actor_account_id=current_account.id,
        actor_role=current_account.role,
        metadata={'previous_status': previous_status, 'new_status': 'canceled'}
    )
    db.session.commit()

    _emit_facility_appointment('facility:appointment_updated', resolved_facility_id, appointment)
    _notify_mother_facility_appointment(appointment, 'facility:appointment_updated')
    _notify_assigned_facility_staff_for_appointment(appointment)

    return jsonify({
        'message': 'Appointment canceled',
        'appointment': _serialize_nurse_compat_appointment(appointment),
    }), 200


@bp.route('/facilities/<int:facility_id>/nurse-compat/appointments/<int:appointment_id>/restore', methods=['POST'])
@require_facility_auth
def restore_nurse_compat_appointment(facility_id, appointment_id):
    current_account = request.current_facility_account
    resolved = _ensure_nurse_compat_scope(current_account, facility_id)
    if len(resolved) != 4:
        return resolved

    resolved_facility_id, is_admin, _membership, _role = resolved
    appointment = FacilityAppointment.query.get(appointment_id)
    if not appointment or appointment.facility_id != resolved_facility_id:
        return jsonify({'error': 'Appointment not found'}), 404

    if not is_admin:
        return jsonify({'error': 'Only facility admin can restore canceled appointments'}), 403

    if appointment.status != 'canceled':
        return jsonify({'error': 'Only canceled appointments can be restored'}), 400

    appointment.status = 'scheduled'
    _apply_facility_ticket_state_for_status(appointment, 'scheduled')
    appointment.updated_at = datetime.now(timezone.utc)
    _log_facility_ticket_event(
        appointment,
        'rescheduled',
        actor_account_id=current_account.id,
        actor_role=current_account.role,
        metadata={'previous_status': 'canceled', 'new_status': 'scheduled'}
    )
    db.session.commit()

    _emit_facility_appointment('facility:appointment_updated', resolved_facility_id, appointment)
    _notify_mother_facility_appointment(appointment, 'facility:appointment_updated')
    _notify_assigned_facility_staff_for_appointment(appointment)

    return jsonify({
        'message': 'Appointment restored',
        'appointment': _serialize_nurse_compat_appointment(appointment),
    }), 200


@bp.route('/facilities/<int:facility_id>/nurse-compat/team/chws', methods=['GET'])
@require_facility_auth
def list_nurse_compat_team_chws(facility_id):
    current_account = request.current_facility_account
    resolved = _ensure_nurse_compat_scope(current_account, facility_id)
    if len(resolved) != 4:
        return resolved

    resolved_facility_id, _is_admin, _membership, _role = resolved
    rows = FacilityEscalation.query.filter(
        FacilityEscalation.facility_id == resolved_facility_id,
        FacilityEscalation.chw_id.isnot(None),
    ).order_by(FacilityEscalation.updated_at.desc()).all()

    aggregates = defaultdict(lambda: {
        'assigned_mothers': set(),
        'active_cases': 0,
        'last_active': None,
    })

    for row in rows:
        agg = aggregates[row.chw_id]
        if row.mother_id:
            agg['assigned_mothers'].add(row.mother_id)
        if row.status in {'received', 'in_progress'}:
            agg['active_cases'] += 1
        latest_touch = row.updated_at or row.created_at
        if latest_touch and (agg['last_active'] is None or latest_touch > agg['last_active']):
            agg['last_active'] = latest_touch

    chws = []
    for chw_id, agg in aggregates.items():
        chw = CHW.query.get(chw_id)
        if not chw:
            continue

        phone_number = chw.user.phone_number if chw.user else None
        chws.append({
            'id': chw.id,
            'user_id': chw.user_id,
            'name': chw.chw_name,
            'phone_number': phone_number,
            'location': chw.location,
            'assigned_mothers': len(agg['assigned_mothers']),
            'active_cases': agg['active_cases'],
            'performance': 100,
            'last_active': agg['last_active'].isoformat() if agg['last_active'] else None,
        })

    chws.sort(key=lambda item: ((item.get('last_active') or ''), item.get('name') or ''), reverse=True)

    return jsonify({
        'facility_id': resolved_facility_id,
        'total': len(chws),
        'chws': chws,
    }), 200


@bp.route('/facilities/<int:facility_id>/nurse-compat/chws/<int:chw_id>/mothers', methods=['GET'])
@require_facility_auth
def list_nurse_compat_chw_mothers(facility_id, chw_id):
    current_account = request.current_facility_account
    resolved = _ensure_nurse_compat_scope(current_account, facility_id)
    if len(resolved) != 4:
        return resolved

    resolved_facility_id, _is_admin, _membership, _role = resolved
    rows = FacilityEscalation.query.filter(
        FacilityEscalation.facility_id == resolved_facility_id,
        FacilityEscalation.chw_id == chw_id,
        FacilityEscalation.mother_id.isnot(None),
    ).order_by(FacilityEscalation.updated_at.desc()).all()

    mothers_map = {}
    for row in rows:
        if row.mother_id in mothers_map:
            continue
        mother = Mother.query.get(row.mother_id)
        if not mother:
            continue
        mothers_map[mother.id] = {
            'assignment_id': row.id,
            'mother_id': mother.id,
            'user_id': mother.user_id,
            'name': mother.mother_name,
            'phone_number': mother.user.phone_number if mother.user else None,
            'location': mother.location,
            'status': 'active',
            'checkin_status': None,
            'last_check_in_at': None,
            'due_date': mother.due_date.isoformat() if mother.due_date else None,
            'weeks_pregnant': None,
            'risk_level': None,
            'last_ultrasound_at': None,
            'assigned_at': (row.created_at.isoformat() if row.created_at else datetime.now(timezone.utc).isoformat()),
        }

    mothers = list(mothers_map.values())
    return jsonify({'mothers': mothers, 'total': len(mothers)}), 200


@bp.route('/facilities/<int:facility_id>/nurse-compat/mothers/<int:mother_id>/ultrasound', methods=['POST'])
@require_facility_auth
def create_nurse_compat_ultrasound(facility_id, mother_id):
    current_account = request.current_facility_account
    resolved = _ensure_nurse_compat_scope(current_account, facility_id)
    if len(resolved) != 4:
        return resolved

    resolved_facility_id, _is_admin, _membership, _role = resolved
    mother = Mother.query.get(mother_id)
    if not mother:
        return jsonify({'error': 'Mother not found'}), 404

    # Must belong to this facility context via escalations history.
    link_exists = FacilityEscalation.query.filter(
        FacilityEscalation.facility_id == resolved_facility_id,
        FacilityEscalation.mother_id == mother.id,
    ).first()
    if not link_exists:
        return jsonify({'error': 'Mother is not linked to this facility context'}), 403

    linked_user = _resolve_user_for_facility_account(current_account)
    if not linked_user:
        return jsonify({'error': 'Facility account is not linked to a user profile for ultrasound recording'}), 400

    data = request.get_json() or {}
    week_number = data.get('week_number')
    scan_date = data.get('scan_date')
    if not week_number or not scan_date:
        return jsonify({'error': 'week_number and scan_date are required'}), 400

    try:
        week_number = int(week_number)
        if week_number < 1 or week_number > 42:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({'error': 'week_number must be between 1 and 42'}), 400

    try:
        parsed_scan_date = datetime.strptime(str(scan_date), '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'scan_date must be in YYYY-MM-DD format'}), 400

    row = UltrasoundRecord(
        mother_id=mother.id,
        week_number=week_number,
        fetal_weight_grams=data.get('fetal_weight_grams'),
        fetal_length_cm=data.get('fetal_length_cm'),
        heart_rate_bpm=data.get('heart_rate_bpm'),
        notes=(data.get('notes') or '').strip() or None,
        recorded_by=linked_user.id,
        scan_date=parsed_scan_date,
        created_at=datetime.now(timezone.utc),
    )

    db.session.add(row)
    db.session.commit()

    payload = {
        'id': row.id,
        'mother_id': row.mother_id,
        'week_number': row.week_number,
        'fetal_weight_grams': float(row.fetal_weight_grams) if row.fetal_weight_grams is not None else None,
        'fetal_length_cm': float(row.fetal_length_cm) if row.fetal_length_cm is not None else None,
        'heart_rate_bpm': row.heart_rate_bpm,
        'notes': row.notes,
        'recorded_by': row.recorded_by,
        'scan_date': row.scan_date.isoformat() if row.scan_date else None,
        'created_at': row.created_at.isoformat() if row.created_at else None,
    }

    socketio.emit('ultrasound:created', payload, to=f'facility:{resolved_facility_id}')
    if mother.user_id:
        socketio.emit('ultrasound:created', payload, to=f'user:{mother.user_id}')

    return jsonify({'message': 'Ultrasound record saved.', **payload}), 201


@bp.route('/facilities/<int:facility_id>/nurse-compat/resources', methods=['GET'])
@require_facility_auth
def list_nurse_compat_resources(facility_id):
    current_account = request.current_facility_account
    resolved = _ensure_nurse_compat_scope(current_account, facility_id)
    if len(resolved) != 4:
        return resolved

    role = (request.args.get('role') or 'nurse').strip().lower()
    query = Resource.query
    if role in {'mother', 'chw', 'nurse'}:
        query = query.filter_by(target_role=role)

    rows = query.order_by(Resource.created_at.desc()).all()
    payload = [{
        'id': row.id,
        'title': row.title,
        'description': row.description,
        'category': row.category,
        'target_role': row.target_role,
        'content_type': row.content_type,
        'url': row.url,
        'thumbnail': row.thumbnail,
        'created_at': row.created_at.isoformat() if row.created_at else None,
    } for row in rows]

    return jsonify({'data': payload, 'count': len(payload)}), 200


@bp.route('/facilities/<int:facility_id>/nurse-compat/notifications', methods=['GET'])
@require_facility_auth
def list_nurse_compat_notifications(facility_id):
    current_account = request.current_facility_account
    resolved = _ensure_nurse_compat_scope(current_account, facility_id)
    if len(resolved) != 4:
        return resolved

    linked_user = _resolve_user_for_facility_account(current_account)
    if not linked_user:
        return jsonify({'notifications': [], 'unread_count': 0, 'total': 0}), 200

    limit = request.args.get('limit', default=20, type=int)
    limit = max(1, min(limit, 100))
    unread_only = str(request.args.get('unread_only', 'false')).lower() in {'1', 'true', 'yes'}

    query = UserNotification.query.filter(UserNotification.user_id == linked_user.id)
    if unread_only:
        query = query.filter(UserNotification.is_read.is_(False))

    rows = query.order_by(UserNotification.created_at.desc()).limit(limit).all()
    unread_count = UserNotification.query.filter(
        UserNotification.user_id == linked_user.id,
        UserNotification.is_read.is_(False),
    ).count()

    return jsonify({
        'notifications': [_serialize_user_notification(row) for row in rows],
        'unread_count': unread_count,
        'total': len(rows),
    }), 200


@bp.route('/facilities/<int:facility_id>/nurse-compat/notifications/unread-count', methods=['GET'])
@require_facility_auth
def nurse_compat_notification_unread_count(facility_id):
    current_account = request.current_facility_account
    resolved = _ensure_nurse_compat_scope(current_account, facility_id)
    if len(resolved) != 4:
        return resolved

    linked_user = _resolve_user_for_facility_account(current_account)
    if not linked_user:
        return jsonify({'unread_count': 0}), 200

    unread_count = UserNotification.query.filter(
        UserNotification.user_id == linked_user.id,
        UserNotification.is_read.is_(False),
    ).count()
    return jsonify({'unread_count': unread_count}), 200


@bp.route('/facilities/<int:facility_id>/nurse-compat/notifications/<int:notification_id>/read', methods=['PATCH'])
@require_facility_auth
def mark_nurse_compat_notification_read(facility_id, notification_id):
    current_account = request.current_facility_account
    resolved = _ensure_nurse_compat_scope(current_account, facility_id)
    if len(resolved) != 4:
        return resolved

    linked_user = _resolve_user_for_facility_account(current_account)
    if not linked_user:
        return jsonify({'error': 'Notification not found'}), 404

    row = UserNotification.query.filter_by(id=notification_id, user_id=linked_user.id).first()
    if not row:
        return jsonify({'error': 'Notification not found'}), 404

    if not row.is_read:
        row.is_read = True
        row.read_at = datetime.now(timezone.utc)
        db.session.commit()

    unread_count = UserNotification.query.filter(
        UserNotification.user_id == linked_user.id,
        UserNotification.is_read.is_(False),
    ).count()
    return jsonify({'message': 'Notification marked as read.', 'unread_count': unread_count}), 200


@bp.route('/facilities/<int:facility_id>/nurse-compat/notifications/read-all', methods=['PATCH'])
@require_facility_auth
def mark_all_nurse_compat_notifications_read(facility_id):
    current_account = request.current_facility_account
    resolved = _ensure_nurse_compat_scope(current_account, facility_id)
    if len(resolved) != 4:
        return resolved

    linked_user = _resolve_user_for_facility_account(current_account)
    if not linked_user:
        return jsonify({'message': 'All notifications marked as read.', 'unread_count': 0}), 200

    db.session.query(UserNotification).filter(
        UserNotification.user_id == linked_user.id,
        UserNotification.is_read.is_(False),
    ).update({'is_read': True, 'read_at': datetime.now(timezone.utc)}, synchronize_session=False)
    db.session.commit()

    return jsonify({'message': 'All notifications marked as read.', 'unread_count': 0}), 200


@bp.route('/facilities/staff', methods=['GET'])
@require_facility_auth
def list_facility_staff():
    current_account = request.current_facility_account
    facility_id = request.args.get('facility_id', type=int)

    admin_facility = _admin_facility_for_account(current_account, facility_id)

    if admin_facility:
        resolved_facility_id = admin_facility.id
        is_admin = True
    else:
        membership = _active_membership(current_account.id, facility_id)
        if not membership:
            return jsonify({'error': 'Not allowed to view this facility staff list'}), 403
        resolved_facility_id = membership.facility_id
        is_admin = False

    staff_rows = FacilityStaff.query.filter_by(facility_id=resolved_facility_id).order_by(FacilityStaff.added_at.desc()).all()

    return jsonify({
        'facility_id': resolved_facility_id,
        'is_admin': is_admin,
        'count': len(staff_rows),
        'staff': [row.to_dict() for row in staff_rows],
    }), 200


@bp.route('/facilities/staff/<int:staff_id>', methods=['PATCH'])
@require_facility_auth
def update_facility_staff(staff_id):
    current_account = request.current_facility_account
    data = request.get_json() or {}

    staff_row = FacilityStaff.query.get(staff_id)
    if not staff_row:
        return jsonify({'error': 'Staff membership not found'}), 404

    admin_facility = _admin_facility_for_account(current_account, staff_row.facility_id)
    if not admin_facility:
        return jsonify({'error': 'Only facility admin can update staff'}), 403

    role = data.get('role')
    status = data.get('status')
    specialty = data.get('specialty')

    if role is not None:
        role = role.strip().lower()
        if role not in ASSIGNABLE_MEMBER_ROLES:
            return jsonify({'error': f'role must be one of {sorted(ASSIGNABLE_MEMBER_ROLES)}'}), 400
        staff_row.role = role
        if staff_row.account:
            staff_row.account.role = role

    if status is not None:
        status = status.strip().lower()
        if status not in ALLOWED_STAFF_STATUSES:
            return jsonify({'error': f'status must be one of {sorted(ALLOWED_STAFF_STATUSES)}'}), 400
        staff_row.status = status
        if staff_row.account:
            staff_row.account.is_active = status != 'removed'

    if specialty is not None:
        staff_row.specialty = specialty.strip() or None

    db.session.commit()

    _emit_facility_staff_update(staff_row.facility_id)

    return jsonify({
        'message': 'Staff record updated',
        'staff': staff_row.to_dict(),
    }), 200


@bp.route('/facilities/<int:facility_id>/dashboard', methods=['GET'])
@require_facility_auth
def get_facility_dashboard_summary(facility_id):
    current_account = request.current_facility_account

    membership = _active_membership(current_account.id, facility_id)
    if not membership and not _admin_facility_for_account(current_account, facility_id):
        return jsonify({'error': 'Access denied for this facility'}), 403

    facility = HealthFacility.query.get(facility_id)
    if not facility:
        return jsonify({'error': 'Facility not found'}), 404

    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    staff_count = FacilityStaff.query.filter_by(facility_id=facility_id, status='active').count()
    monthly_appointments = FacilityAppointment.query.filter(
        FacilityAppointment.facility_id == facility_id,
        FacilityAppointment.created_at >= month_start,
    ).count()

    return jsonify({
        'facility': {
            'id': facility.id,
            'name': facility.name,
            'address': facility.address,
            'city': facility.city,
            'phone': facility.phone,
            'email': facility.email,
            'hours_text': facility.hours_text,
        },
        'stats': {
            'staff_count': staff_count,
            'appointments_this_month': monthly_appointments,
        },
    }), 200


@bp.route('/facilities/<int:facility_id>/settings', methods=['PATCH'])
@require_facility_auth
def update_facility_settings(facility_id):
    current_account = request.current_facility_account
    facility = _admin_facility_for_account(current_account, facility_id)
    if not facility:
        return jsonify({'error': 'Only facility admin can update settings'}), 403

    data = request.get_json() or {}
    facility.phone = (data.get('phone') or '').strip() or None
    facility.email = (data.get('email') or '').strip().lower() or None
    facility.hours_text = (data.get('hours_text') or '').strip() or None
    facility.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({
        'message': 'Facility settings updated',
        'facility': {
            'id': facility.id,
            'phone': facility.phone,
            'email': facility.email,
            'hours_text': facility.hours_text,
        },
    }), 200


@bp.route('/facilities/<int:facility_id>/appointments', methods=['GET'])
@require_facility_auth
def list_facility_appointments(facility_id):
    current_account = request.current_facility_account

    membership = _active_membership(current_account.id, facility_id)
    if not membership and not _admin_facility_for_account(current_account, facility_id):
        return jsonify({'error': 'Access denied for this facility'}), 403

    status_filter = (request.args.get('status') or '').strip().lower()

    query = FacilityAppointment.query.filter_by(facility_id=facility_id)
    if status_filter:
        query = query.filter(FacilityAppointment.status == status_filter)

    rows = query.order_by(FacilityAppointment.scheduled_time.asc()).all()

    return jsonify({
        'facility_id': facility_id,
        'count': len(rows),
        'appointments': [row.to_dict() for row in rows],
    }), 200


@bp.route('/facilities/<int:facility_id>/appointments', methods=['POST'])
@require_facility_auth
def create_facility_appointment(facility_id):
    current_account = request.current_facility_account
    data = request.get_json() or {}

    facility = _admin_facility_for_account(current_account, facility_id)
    if not facility:
        return jsonify({'error': 'Only facility admin can create appointments'}), 403

    scheduled_time = _parse_iso_datetime(data.get('scheduled_time'))
    if not scheduled_time:
        return jsonify({'error': 'valid scheduled_time is required'}), 400
    minimum_time_error = _validate_minimum_schedule_time(scheduled_time)
    if minimum_time_error:
        return minimum_time_error
    mother_id, mother_name, mother_resolution_error = _resolve_mother_for_appointment(
        mother_id=data.get('mother_id'),
        mother_phone_number=data.get('mother_phone_number'),
    )
    if mother_resolution_error:
        return mother_resolution_error

    appointment = FacilityAppointment(
        facility_id=facility_id,
        mother_id=mother_id,
        mother_name=mother_name,
        scheduled_time=scheduled_time,
        appointment_type=(data.get('appointment_type') or '').strip() or None,
        status='scheduled',
        created_by_account_id=current_account.id,
        notes=(data.get('notes') or '').strip() or None,
        ticket_code=_create_facility_appointment_ticket_code(),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    _apply_facility_ticket_state_for_status(appointment, appointment.status)

    db.session.add(appointment)
    db.session.flush()
    _log_facility_ticket_event(
        appointment,
        'generated',
        actor_account_id=current_account.id,
        actor_role=current_account.role,
        metadata={'scheduled_time': appointment.scheduled_time.isoformat() if appointment.scheduled_time else None}
    )
    db.session.commit()

    _emit_facility_appointment('facility:appointment_created', facility_id, appointment)
    _notify_mother_facility_appointment(appointment, 'facility:appointment_created')
    _notify_facility_admin_for_new_appointment(appointment)

    return jsonify({
        'message': 'Facility appointment created',
        'appointment': appointment.to_dict(),
    }), 201


@bp.route('/facilities/<int:facility_id>/appointments/<int:appointment_id>/assign', methods=['POST'])
@require_facility_auth
def assign_facility_appointment(facility_id, appointment_id):
    current_account = request.current_facility_account

    membership = _active_membership(current_account.id, facility_id)
    if not membership:
        return jsonify({'error': 'Only active facility members can claim appointments'}), 403

    appointment = FacilityAppointment.query.get(appointment_id)
    if not appointment or appointment.facility_id != facility_id:
        return jsonify({'error': 'Appointment not found'}), 404

    if appointment.status in {'completed', 'canceled'}:
        return jsonify({'error': 'Completed/canceled appointments cannot be assigned'}), 400

    if appointment.assigned_staff_account_id and appointment.assigned_staff_account_id != current_account.id:
        return jsonify({'error': 'Appointment is already assigned to another staff member'}), 409

    appointment.assigned_staff_account_id = current_account.id
    appointment.status = 'assigned'
    appointment.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    _emit_facility_appointment('facility:appointment_updated', facility_id, appointment)
    _notify_mother_facility_appointment(appointment, 'facility:appointment_updated')
    _notify_assigned_facility_staff_for_appointment(appointment)

    return jsonify({
        'message': 'Appointment assigned successfully',
        'appointment': appointment.to_dict(),
    }), 200


@bp.route('/facilities/<int:facility_id>/appointments/<int:appointment_id>/status', methods=['PATCH'])
@require_facility_auth
def update_facility_appointment_status(facility_id, appointment_id):
    """Update appointment status (complete / cancel / revert to scheduled)."""
    current_account = request.current_facility_account

    membership = _active_membership(current_account.id, facility_id)
    is_admin = bool(_admin_facility_for_account(current_account, facility_id))
    if not membership and not is_admin:
        return jsonify({'error': 'Only active facility members can update appointments'}), 403

    appointment = FacilityAppointment.query.get(appointment_id)
    if not appointment or appointment.facility_id != facility_id:
        return jsonify({'error': 'Appointment not found'}), 404

    if not is_admin and appointment.assigned_staff_account_id != current_account.id:
        return jsonify({'error': 'Only the assigned staff member can update this appointment'}), 403

    data = request.get_json() or {}
    new_status = (data.get('status') or '').strip().lower()

    allowed = {'scheduled', 'assigned', 'completed', 'canceled'}
    if new_status not in allowed:
        return jsonify({'error': f'status must be one of {sorted(allowed)}'}), 400

    # Non-admin members can only resolve their own assigned appointments.
    if not is_admin and new_status in {'scheduled', 'assigned'}:
        return jsonify({'error': 'Only facility admin can set scheduled/assigned status manually'}), 403

    previous_status = appointment.status
    appointment.status = new_status
    _apply_facility_ticket_state_for_status(
        appointment,
        new_status,
        actor_account_id=current_account.id if new_status == 'completed' else None,
        validation_method=appointment.validation_method,
    )
    appointment.updated_at = datetime.now(timezone.utc)
    if previous_status != new_status:
        event_type = 'canceled' if new_status == 'canceled' else 'validated' if new_status == 'completed' else 'rescheduled' if new_status == 'scheduled' else None
        if event_type:
            _log_facility_ticket_event(
                appointment,
                event_type,
                actor_account_id=current_account.id,
                actor_role=current_account.role,
                metadata={'previous_status': previous_status, 'new_status': new_status}
            )
    db.session.commit()

    _emit_facility_appointment('facility:appointment_updated', facility_id, appointment)
    _notify_mother_facility_appointment(appointment, 'facility:appointment_updated')
    _notify_assigned_facility_staff_for_appointment(appointment)

    return jsonify({
        'message': f'Appointment status updated to {new_status}',
        'appointment': appointment.to_dict(),
    }), 200


@bp.route('/facilities/<int:facility_id>/appointments/<int:appointment_id>', methods=['PATCH'])
@require_facility_auth
def update_facility_appointment(facility_id, appointment_id):
    current_account = request.current_facility_account

    membership = _active_membership(current_account.id, facility_id)
    is_admin = bool(_admin_facility_for_account(current_account, facility_id))
    if not membership and not is_admin:
        return jsonify({'error': 'Only active facility members can update appointments'}), 403

    appointment = FacilityAppointment.query.get(appointment_id)
    if not appointment or appointment.facility_id != facility_id:
        return jsonify({'error': 'Appointment not found'}), 404

    if appointment.created_by_account_id != current_account.id:
        return jsonify({'error': 'Only the facility account that created this appointment can edit it'}), 403

    if appointment.status == 'completed':
        return jsonify({'error': 'Completed appointments cannot be edited'}), 400

    data = request.get_json() or {}
    previous_scheduled_time = appointment.scheduled_time.isoformat() if appointment.scheduled_time else None
    scheduled_time_changed = False

    if 'scheduled_time' in data:
      parsed = _parse_iso_datetime(data.get('scheduled_time'))
      if not parsed:
          return jsonify({'error': 'valid scheduled_time is required'}), 400
      minimum_time_error = _validate_minimum_schedule_time(parsed)
      if minimum_time_error:
          return minimum_time_error
      appointment.scheduled_time = parsed
      scheduled_time_changed = appointment.scheduled_time.isoformat() != previous_scheduled_time

    if 'appointment_type' in data:
        appointment.appointment_type = (data.get('appointment_type') or '').strip() or None

    if 'notes' in data:
        appointment.notes = (data.get('notes') or '').strip() or None

    appointment.mother_response_status = None
    appointment.mother_response_note = None
    appointment.mother_responded_at = None
    appointment.updated_at = datetime.now(timezone.utc)
    if scheduled_time_changed:
        _apply_facility_ticket_state_for_status(appointment, 'scheduled')
        _log_facility_ticket_event(
            appointment,
            'rescheduled',
            actor_account_id=current_account.id,
            actor_role=current_account.role,
            metadata={
                'previous_scheduled_time': previous_scheduled_time,
                'new_scheduled_time': appointment.scheduled_time.isoformat(),
            }
        )

    db.session.commit()

    _emit_facility_appointment('facility:appointment_updated', facility_id, appointment)
    _notify_mother_facility_appointment(appointment, 'facility:appointment_updated')
    _notify_assigned_facility_staff_for_appointment(appointment)

    return jsonify({
        'message': 'Appointment updated',
        'appointment': appointment.to_dict(),
    }), 200


@bp.route('/facilities/<int:facility_id>/appointments/<int:appointment_id>', methods=['DELETE'])
@require_facility_auth
def cancel_facility_appointment(facility_id, appointment_id):
    current_account = request.current_facility_account

    membership = _active_membership(current_account.id, facility_id)
    is_admin = bool(_admin_facility_for_account(current_account, facility_id))
    if not membership and not is_admin:
        return jsonify({'error': 'Only active facility members can update appointments'}), 403

    appointment = FacilityAppointment.query.get(appointment_id)
    if not appointment or appointment.facility_id != facility_id:
        return jsonify({'error': 'Appointment not found'}), 404

    if appointment.created_by_account_id != current_account.id:
        return jsonify({'error': 'Only the facility account that created this appointment can cancel it'}), 403
    if appointment.status == 'completed':
        return jsonify({'error': 'Completed appointments cannot be canceled'}), 400
    if appointment.status == 'canceled':
        return jsonify({'error': 'Appointment is already canceled'}), 400

    previous_status = appointment.status
    appointment.status = 'canceled'
    appointment.updated_at = datetime.now(timezone.utc)
    _apply_facility_ticket_state_for_status(appointment, 'canceled')
    _log_facility_ticket_event(
        appointment,
        'canceled',
        actor_account_id=current_account.id,
        actor_role=current_account.role,
        metadata={'previous_status': previous_status, 'new_status': 'canceled'}
    )
    db.session.commit()

    _emit_facility_appointment('facility:appointment_updated', facility_id, appointment)
    _notify_mother_facility_appointment(appointment, 'facility:appointment_updated')
    _notify_assigned_facility_staff_for_appointment(appointment)

    return jsonify({
        'message': 'Appointment canceled',
        'appointment': appointment.to_dict(),
    }), 200


@bp.route('/facilities/<int:facility_id>/appointments/<int:appointment_id>/restore', methods=['POST'])
@require_facility_auth
def restore_facility_appointment(facility_id, appointment_id):
    current_account = request.current_facility_account

    membership = _active_membership(current_account.id, facility_id)
    is_admin = bool(_admin_facility_for_account(current_account, facility_id))
    if not membership and not is_admin:
        return jsonify({'error': 'Only active facility members can update appointments'}), 403

    appointment = FacilityAppointment.query.get(appointment_id)
    if not appointment or appointment.facility_id != facility_id:
        return jsonify({'error': 'Appointment not found'}), 404

    if appointment.created_by_account_id != current_account.id:
        return jsonify({'error': 'Only the facility account that created this appointment can restore it'}), 403
    if appointment.status != 'canceled':
        return jsonify({'error': 'Only canceled appointments can be restored'}), 400

    minimum_time_error = _validate_minimum_schedule_time(appointment.scheduled_time)
    if minimum_time_error:
        return minimum_time_error

    appointment.status = 'scheduled'
    appointment.mother_response_status = None
    appointment.mother_response_note = None
    appointment.mother_responded_at = None
    appointment.updated_at = datetime.now(timezone.utc)
    _apply_facility_ticket_state_for_status(appointment, 'scheduled')
    _log_facility_ticket_event(
        appointment,
        'rescheduled',
        actor_account_id=current_account.id,
        actor_role=current_account.role,
        metadata={'previous_status': 'canceled', 'new_status': 'scheduled'}
    )
    db.session.commit()

    _emit_facility_appointment('facility:appointment_updated', facility_id, appointment)
    _notify_mother_facility_appointment(appointment, 'facility:appointment_updated')
    _notify_assigned_facility_staff_for_appointment(appointment)

    return jsonify({
        'message': 'Appointment restored',
        'appointment': appointment.to_dict(),
    }), 200


# ============================================================
# FACILITY ESCALATIONS (STAFF-MEMBER PARITY FLOW)
# ============================================================

@bp.route('/staff-members/escalations', methods=['GET'])
@require_facility_auth
def list_staff_member_escalations():
    current_account = request.current_facility_account
    facility_id = request.args.get('facility_id', type=int)

    resolved = _resolve_facility_scope(current_account, facility_id)
    if len(resolved) == 3:
        resolved_facility_id, is_admin, _membership = resolved
    else:
        return resolved

    status_filter = _normalize_facility_escalation_status(request.args.get('status'))
    priority_filter = (request.args.get('priority') or '').strip().lower()
    assigned_only = str(request.args.get('assigned_to_me', 'false')).lower() in ('1', 'true', 'yes')

    query = FacilityEscalation.query.filter_by(facility_id=resolved_facility_id)
    if status_filter:
        query = query.filter(FacilityEscalation.status == status_filter)
    if priority_filter:
        query = query.filter(FacilityEscalation.priority == priority_filter)
    if assigned_only:
        query = query.filter(FacilityEscalation.assigned_staff_account_id == current_account.id)

    rows = query.order_by(FacilityEscalation.created_at.desc()).all()
    return jsonify({
        'facility_id': resolved_facility_id,
        'is_admin': is_admin,
        'count': len(rows),
        'escalations': [_escalation_payload_with_permissions(row, is_admin) for row in rows],
    }), 200


@bp.route('/facilities/<int:facility_id>/escalations', methods=['GET'])
@require_facility_auth
def list_facility_escalations_alias(facility_id):
    current_account = request.current_facility_account
    resolved = _resolve_facility_scope(current_account, facility_id)
    if len(resolved) == 3:
        resolved_facility_id, is_admin, _membership = resolved
    else:
        return resolved

    status_filter = _normalize_facility_escalation_status(request.args.get('status'))
    priority_filter = (request.args.get('priority') or '').strip().lower()
    assigned_only = str(request.args.get('assigned_to_me', 'false')).lower() in ('1', 'true', 'yes')

    query = FacilityEscalation.query.filter_by(facility_id=resolved_facility_id)
    if status_filter:
        query = query.filter(FacilityEscalation.status == status_filter)
    if priority_filter:
        query = query.filter(FacilityEscalation.priority == priority_filter)
    if assigned_only:
        query = query.filter(FacilityEscalation.assigned_staff_account_id == current_account.id)

    rows = query.order_by(FacilityEscalation.created_at.desc()).all()
    return jsonify({
        'facility_id': resolved_facility_id,
        'is_admin': is_admin,
        'count': len(rows),
        'escalations': [_escalation_payload_with_permissions(row, is_admin) for row in rows],
    }), 200


@bp.route('/staff-members/escalations/<int:escalation_id>', methods=['GET'])
@require_facility_auth
def get_staff_member_escalation(escalation_id):
    current_account = request.current_facility_account
    row = FacilityEscalation.query.get(escalation_id)
    if not row:
        return jsonify({'error': 'Escalation not found'}), 404

    resolved = _resolve_facility_scope(current_account, row.facility_id)
    if len(resolved) != 3:
        return resolved
    _, is_admin, _membership = resolved

    return jsonify(_escalation_payload_with_permissions(row, is_admin)), 200


@bp.route('/facilities/<int:facility_id>/escalations/<int:escalation_id>', methods=['GET'])
@require_facility_auth
def get_facility_escalation_alias(facility_id, escalation_id):
    _ = facility_id
    return get_staff_member_escalation(escalation_id)


@bp.route('/staff-members/escalations/<int:escalation_id>/assign', methods=['PATCH'])
@require_facility_auth
def assign_staff_member_escalation(escalation_id):
    current_account = request.current_facility_account
    row = FacilityEscalation.query.get(escalation_id)
    if not row:
        return jsonify({'error': 'Escalation not found'}), 404

    resolved = _resolve_facility_scope(current_account, row.facility_id)
    if len(resolved) != 3:
        return resolved
    _, is_admin, _membership = resolved
    if not is_admin:
        return jsonify({'error': 'Only facility admin can assign escalations'}), 403

    data = request.get_json() or {}
    assigned_staff_account_id = data.get('assigned_staff_account_id')
    if not assigned_staff_account_id:
        return jsonify({'error': 'assigned_staff_account_id is required'}), 400

    target_account = FacilityAccount.query.get(assigned_staff_account_id)
    if not target_account or target_account.facility_id != row.facility_id:
        return jsonify({'error': 'Assigned staff account not found in this facility'}), 404

    target_membership = FacilityStaff.query.filter_by(
        facility_id=row.facility_id,
        account_id=target_account.id,
        status='active',
    ).first()
    if not target_membership:
        return jsonify({'error': 'Assigned staff is not active in this facility'}), 400
    if target_membership.role not in ASSIGNABLE_MEMBER_ROLES:
        return jsonify({'error': f"Assigned staff role must be one of {sorted(ASSIGNABLE_MEMBER_ROLES)}"}), 400

    row.assigned_staff_account_id = target_account.id
    row.assigned_staff_role = target_membership.role
    row.updated_by_account_id = current_account.id
    row.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    _emit_facility_escalation('facility:escalation_updated', row)
    _notify_facility_staff_assignment(row, target_account, current_account)

    return jsonify({
        'message': 'Escalation assigned successfully',
        'escalation': _escalation_payload_with_permissions(row, True),
    }), 200


@bp.route('/facilities/<int:facility_id>/escalations/<int:escalation_id>/assign', methods=['PATCH'])
@require_facility_auth
def assign_facility_escalation_alias(facility_id, escalation_id):
    _ = facility_id
    return assign_staff_member_escalation(escalation_id)


@bp.route('/staff-members/escalations/<int:escalation_id>/status', methods=['PATCH'])
@require_facility_auth
def update_staff_member_escalation_status(escalation_id):
    current_account = request.current_facility_account
    row = FacilityEscalation.query.get(escalation_id)
    if not row:
        return jsonify({'error': 'Escalation not found'}), 404

    resolved = _resolve_facility_scope(current_account, row.facility_id)
    if len(resolved) != 3:
        return resolved
    _, is_admin, _membership = resolved
    if not is_admin:
        return jsonify({'error': 'Only facility admin can update escalation status'}), 403

    data = request.get_json() or {}
    new_status = _normalize_facility_escalation_status(data.get('status'))
    if new_status not in FACILITY_ESCALATION_STATUSES:
        return jsonify({'error': f'status must be one of {sorted(FACILITY_ESCALATION_STATUSES)}'}), 400

    row.status = new_status
    row.updated_by_account_id = current_account.id
    row.updated_at = datetime.now(timezone.utc)
    row.checked_out_at = datetime.now(timezone.utc) if new_status == 'checked_out' else None
    if 'notes' in data:
        row.notes = (data.get('notes') or '').strip() or row.notes

    db.session.commit()

    _emit_facility_escalation('facility:escalation_updated', row)
    _notify_facility_escalation_status_change(row)
    _notify_facility_admin_status_update(row, current_account)
    _notify_assigned_staff_status_update(row, current_account)

    return jsonify({
        'message': f'Escalation status updated to {new_status}',
        'escalation': _escalation_payload_with_permissions(row, True),
    }), 200


@bp.route('/facilities/<int:facility_id>/escalations/<int:escalation_id>/status', methods=['PATCH'])
@require_facility_auth
def update_facility_escalation_status_alias(facility_id, escalation_id):
    _ = facility_id
    return update_staff_member_escalation_status(escalation_id)


@bp.route('/staff-members/escalations/<int:escalation_id>', methods=['PATCH'])
@require_facility_auth
def update_staff_member_escalation(escalation_id):
    current_account = request.current_facility_account
    row = FacilityEscalation.query.get(escalation_id)
    if not row:
        return jsonify({'error': 'Escalation not found'}), 404

    resolved = _resolve_facility_scope(current_account, row.facility_id)
    if len(resolved) != 3:
        return resolved
    _, is_admin, _membership = resolved

    data = request.get_json() or {}
    if is_admin:
        if 'notes' in data:
            row.notes = (data.get('notes') or '').strip() or None
        if 'priority' in data:
            incoming_priority = (data.get('priority') or '').strip().lower()
            if incoming_priority not in {'low', 'medium', 'high', 'critical'}:
                return jsonify({'error': 'priority must be one of low, medium, high, critical'}), 400
            row.priority = incoming_priority
        if 'issue_type' in data:
            row.issue_type = (data.get('issue_type') or '').strip() or None
        if 'case_description' in data:
            case_description = (data.get('case_description') or '').strip()
            if not case_description:
                return jsonify({'error': 'case_description cannot be empty'}), 400
            row.case_description = case_description
    else:
        # Doctor/nurse parity rule: can track and comment but cannot re-prioritize or change assignment/status.
        if 'notes' not in data:
            return jsonify({'error': 'Only notes can be updated by non-admin staff'}), 403
        row.notes = (data.get('notes') or '').strip() or row.notes

    row.updated_by_account_id = current_account.id
    row.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    _emit_facility_escalation('facility:escalation_updated', row)

    return jsonify({
        'message': 'Escalation updated',
        'escalation': _escalation_payload_with_permissions(row, is_admin),
    }), 200


@bp.route('/facilities/<int:facility_id>/escalations/<int:escalation_id>', methods=['PATCH'])
@require_facility_auth
def update_facility_escalation_alias(facility_id, escalation_id):
    _ = facility_id
    return update_staff_member_escalation(escalation_id)


@bp.route('/facilities/<int:facility_id>/escalations', methods=['POST'])
@require_facility_auth
def create_facility_escalation_by_admin(facility_id):
    current_account = request.current_facility_account
    resolved = _resolve_facility_scope(current_account, facility_id)
    if len(resolved) != 3:
        return resolved
    _, is_admin, _membership = resolved
    if not is_admin:
        return jsonify({'error': 'Only facility admin can create manual escalations'}), 403

    data = request.get_json() or {}
    mother_name = (data.get('mother_name') or '').strip()
    case_description = (data.get('case_description') or '').strip()
    if not mother_name or not case_description:
        return jsonify({'error': 'mother_name and case_description are required'}), 400

    row = FacilityEscalation(
        facility_id=facility_id,
        mother_id=data.get('mother_id'),
        mother_user_id=data.get('mother_user_id'),
        mother_name=mother_name,
        chw_id=data.get('chw_id'),
        chw_user_id=data.get('chw_user_id'),
        checkin_id=data.get('checkin_id'),
        case_description=case_description,
        issue_type=(data.get('issue_type') or '').strip() or None,
        notes=(data.get('notes') or '').strip() or None,
        priority=(data.get('priority') or 'medium').strip().lower(),
        status='received',
        created_by_user_id=None,
        updated_by_account_id=current_account.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    if row.priority not in {'low', 'medium', 'high', 'critical'}:
        return jsonify({'error': 'priority must be one of low, medium, high, critical'}), 400

    db.session.add(row)
    db.session.commit()
    _emit_facility_escalation('facility:escalation_created', row)

    return jsonify({
        'message': 'Facility escalation created',
        'escalation': _escalation_payload_with_permissions(row, True),
    }), 201
