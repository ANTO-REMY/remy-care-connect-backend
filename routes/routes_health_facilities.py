"""
Health Facilities API Routes
Endpoints for searching, filtering, and managing health facilities
"""

from flask import Blueprint, request, jsonify
from auth_utils import require_auth, get_current_user
from models import HealthFacility, FacilityAccount, FacilityAppointment, FacilityIssue, FacilityStaff, Mother, AppointmentTicketEvent, User, db
from sqlalchemy import func, or_, text
from datetime import datetime, timezone, timedelta
from socket_manager import socketio
from notifications import create_user_notification, send_push
from push_payloads import build_push_data
import re
import secrets

bp = Blueprint('health_facilities', __name__)
MIN_APPOINTMENT_LEAD_TIME = timedelta(hours=1)

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


def _normalize_csv_values(raw_value: str | None, default_values=None):
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

    if profile == 'maternal_referral' and amenity_values:
        if all(value not in MATERNAL_REFERRAL_AMENITIES for value in amenity_values):
            return 'all'

    return profile

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


def _parse_iso_datetime(value):
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception:
        return None

def _log_facility_ticket_event(appointment, event_type, actor_user_id=None, actor_role=None, metadata=None, notes=None):
    event = AppointmentTicketEvent(
        appointment_source='facility',
        appointment_id=appointment.id,
        ticket_code=appointment.ticket_code,
        event_type=event_type,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        metadata_json=metadata or {},
        notes=notes,
    )
    appointment.ticket_last_event_at = datetime.now(timezone.utc)
    db.session.add(event)


def _apply_facility_ticket_state_for_status(appointment, status):
    if status == 'canceled':
        appointment.ticket_status = 'canceled'
        appointment.validated_at = None
        appointment.validated_by_account_id = None
        appointment.validation_method = None
    elif status == 'completed':
        appointment.ticket_status = 'used'
    else:
        appointment.ticket_status = 'active'
        appointment.validated_at = None
        appointment.validated_by_account_id = None
        appointment.validation_method = None


def _serialize_mother_facility_appointment(row: FacilityAppointment):
    item = row.to_dict()
    facility = row.facility
    item['facility_name'] = facility.name if facility else None
    item['facility_address'] = facility.address if facility else None
    item['facility_city'] = facility.city if facility else None
    item['facility_phone'] = facility.phone if facility else None
    item['facility_email'] = facility.email if facility else None
    item['facility_hours_text'] = facility.hours_text if facility else None
    return item


def _emit_facility_appointment_to_facility_room(event_name: str, appointment: FacilityAppointment):
    socketio.emit(
        event_name,
        _serialize_mother_facility_appointment(appointment),
        to=f'facility:{appointment.facility_id}',
    )


def _notify_facility_about_mother_response(appointment: FacilityAppointment):
    if not appointment.facility:
        return

    targets = []
    seen_account_ids = set()

    for account_id in [appointment.created_by_account_id, appointment.assigned_staff_account_id]:
        if not account_id or account_id in seen_account_ids:
            continue
        account = FacilityAccount.query.get(account_id)
        if not account:
            continue
        seen_account_ids.add(account_id)
        targets.append(account)

    for account in targets:
        linked_user = _resolve_user_for_facility_account(account)
        if not linked_user:
            continue

        response_label = (appointment.mother_response_status or 'commented').replace('_', ' ')
        create_user_notification(
            user_id=linked_user.id,
            event_type='facility:appointment_updated',
            title='Mother Replied To Appointment',
            message=f"{appointment.mother_name} {response_label} the appointment at {appointment.facility.name}.",
            url='/dashboard/facility/appointments',
            entity_type='facility_appointment',
            entity_id=appointment.id,
        )
        send_push(
            linked_user.id,
            'Mother Replied To Appointment',
            f"{appointment.mother_name} {response_label} the appointment.",
            build_push_data(
                event='facility:appointment_updated',
                url='/dashboard/facility/appointments',
                entity_type='facility_appointment',
                entity_id=appointment.id,
                role='facility_staff',
                extra={
                    'facility_id': appointment.facility_id,
                    'facility_name': appointment.facility.name,
                    'mother_name': appointment.mother_name,
                    'response_status': appointment.mother_response_status,
                },
            ),
        )


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


def _ward_link_confidence(matched_by: str):
    if matched_by == 'inferred_ward':
        return 'high'
    if matched_by == 'inferred_subcounty':
        return 'medium'
    return 'low'


def _serialize_ward_linked_facility(facility: HealthFacility, matched_by: str):
    payload = facility.to_dict()
    payload['link_confidence'] = _ward_link_confidence(matched_by)
    payload['link_reason'] = matched_by
    payload['location_quality_status'] = facility.location_quality_status
    payload['inference_source'] = facility.inference_source
    payload['inference_confidence'] = facility.inference_confidence
    return payload


def _notify_facility_dashboard_on_mother_booking(appointment: FacilityAppointment):
    if not appointment.facility:
        return

    staff_accounts = (
        db.session.query(FacilityAccount)
        .join(FacilityStaff, FacilityStaff.account_id == FacilityAccount.id)
        .filter(FacilityStaff.facility_id == appointment.facility_id, FacilityStaff.status == 'active')
        .all()
    )

    notified_user_ids = set()
    for account in staff_accounts:
        linked_user = _resolve_user_for_facility_account(account)
        if not linked_user or linked_user.id in notified_user_ids:
            continue

        notified_user_ids.add(linked_user.id)
        create_user_notification(
            user_id=linked_user.id,
            event_type='facility:appointment_created',
            title='New Appointment Booked by Mother',
            message=f"{appointment.mother_name} booked an appointment at {appointment.facility.name}.",
            url='/dashboard/facility',
            entity_type='facility_appointment',
            entity_id=appointment.id,
        )
        send_push(
            linked_user.id,
            'New Appointment Booked',
            f"{appointment.mother_name} booked an appointment.",
            build_push_data(
                event='facility:appointment_created',
                url='/dashboard/facility',
                entity_type='facility_appointment',
                entity_id=appointment.id,
                role='facility_staff',
                extra={
                    'facility_id': appointment.facility_id,
                    'facility_name': appointment.facility.name,
                    'mother_name': appointment.mother_name,
                    'status': appointment.status,
                },
            ),
        )


def calculate_distance(geometry_wkt, lat, lng):
    """
    Calculate distance in kilometers between facility and point
    Uses PostGIS ST_Distance with geography type
    """
    try:
        # Extract coordinates from WKT: SRID=4326;POINT(lng lat)
        match = re.search(r'POINT\(([^ ]+) ([^ ]+)\)', geometry_wkt)
        if not match:
            return None

        facility_lng = float(match.group(1))
        facility_lat = float(match.group(2))

        # Haversine formula for distance calculation
        from math import radians, sin, cos, sqrt, atan2

        R = 6371  # Earth's radius in kilometers

        lat1, lng1 = radians(facility_lat), radians(facility_lng)
        lat2, lng2 = radians(lat), radians(lng)

        dlat = lat2 - lat1
        dlng = lng2 - lng1

        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))

        distance = R * c
        return round(distance, 2)

    except Exception as e:
        print(f"Error calculating distance: {e}")
        return None


# ============================================================
# SEARCH & DISCOVERY ENDPOINTS
# ============================================================

@bp.route('/health-facilities/search', methods=['GET'])
@require_auth
def search_facilities():
    """
    Search facilities by name, amenity, city, operator type
    
    Query params:
        q: Search query (name)
        amenity: Filter by amenity type (clinic, hospital, pharmacy)
        healthcare: Filter by healthcare type
        city: Filter by city
        operator_type: Filter by operator (private, government, etc.)
        verified: Filter by verification status (true/false)
        limit: Max results (default 20, max 50)
    """
    q = request.args.get('q', '').strip()
    amenity = request.args.get('amenity')
    healthcare = request.args.get('healthcare')
    city = request.args.get('city')
    operator_type = request.args.get('operator_type')
    verified = request.args.get('verified')
    limit = min(int(request.args.get('limit', 20)), 50)
    
    # Build query
    query = HealthFacility.query
    
    # Name search (case-insensitive, partial match)
    if q:
        query = query.filter(HealthFacility.name.ilike(f'%{q}%'))
    
    # Filter by amenity
    if amenity:
        query = query.filter(HealthFacility.amenity == amenity)
    
    # Filter by healthcare type
    if healthcare:
        query = query.filter(HealthFacility.healthcare == healthcare)
    
    # Filter by city
    if city:
        query = query.filter(HealthFacility.city.ilike(f'%{city}%'))
    
    # Filter by operator type
    if operator_type:
        query = query.filter(HealthFacility.operator_type == operator_type)
    
    # Filter by verification status
    if verified is not None:
        verified_bool = verified.lower() == 'true'
        query = query.filter(HealthFacility.verified == verified_bool)
    
    # Order by name
    query = query.order_by(HealthFacility.name)
    
    # Execute query
    results = query.limit(limit).all()
    
    return jsonify({
        'count': len(results),
        'facilities': [f.to_dict() for f in results]
    }), 200


@bp.route('/health-facilities/nearby', methods=['GET'])
@require_auth
def nearby_facilities():
    """
    Find facilities within radius of coordinates
    Uses PostGIS ST_DWithin for spatial filtering (optimized)

    Query params:
        lat: Latitude (required)
        lng: Longitude (required)
        radius_km: Search radius in kilometers (default 10, max 50)
        amenity: Filter by amenity type (optional)
        healthcare: Filter by healthcare type (optional)
        speciality: Filter by speciality (optional)
        limit: Max results (default 20, max 50)
    """
    try:
        lat = float(request.args.get('lat'))
        lng = float(request.args.get('lng'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Valid lat and lng parameters required'}), 400

    radius_km = min(int(request.args.get('radius_km', 10)), 50)
    amenity = request.args.get('amenity')
    healthcare = request.args.get('healthcare')
    speciality = request.args.get('speciality')
    limit = min(int(request.args.get('limit', 20)), 50)

    # Use raw SQL with PostGIS functions for optimal performance
    # ST_DWithin filters by distance in the database (much faster)
    query = db.session.query(
        HealthFacility,
        text(f"ST_Distance(ST_GeomFromText('SRID=4326;POINT({lng} {lat})', 4326), geometry) / 1000 as distance_km")
    ).filter(
        text(f"ST_DWithin(geometry, ST_GeomFromText('SRID=4326;POINT({lng} {lat})', 4326), {radius_km * 1000})")
    )

    # Apply filters
    if amenity:
        query = query.filter(HealthFacility.amenity == amenity)

    if healthcare:
        query = query.filter(HealthFacility.healthcare.ilike(f'%{healthcare}%'))

    if speciality:
        query = query.filter(HealthFacility.healthcare_specialities.contains([speciality]))

    # Order by distance
    query = query.order_by(text("distance_km"))

    results = query.limit(limit).all()

    # Format results
    facilities = []
    for facility, row in results:
        facility_dict = facility.to_dict()
        facility_dict['distance_km'] = round(float(row[1]), 2) if row[1] else 0
        facilities.append(facility_dict)

    return jsonify({
        'count': len(facilities),
        'search_center': {'lat': lat, 'lng': lng},
        'radius_km': radius_km,
        'facilities': facilities
    }), 200


@bp.route('/health-facilities/<int:facility_id>', methods=['GET'])
@require_auth
def get_facility_details(facility_id):
    """
    Get detailed information about a specific facility
    Includes recent issues count
    """
    facility = HealthFacility.query.get(facility_id)
    
    if not facility:
        return jsonify({'error': 'Facility not found'}), 404
    
    # Get facility data
    result = facility.to_dict()
    
    # Add issue statistics
    total_issues = FacilityIssue.query.filter_by(facility_id=facility_id).count()
    open_issues = FacilityIssue.query.filter_by(
        facility_id=facility_id,
        status='reported'
    ).count()
    
    result['issues'] = {
        'total': total_issues,
        'open': open_issues,
        'has_open_issues': open_issues > 0
    }
    
    return jsonify(result), 200


@bp.route('/health-facilities/<int:facility_id>/appointments', methods=['POST'])
@require_auth
def create_mother_facility_appointment(facility_id):
    """Mother books an appointment at a facility (parallel flow to nurse appointments)."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    if user.role != 'mother':
        return jsonify({'error': 'Only mothers can book facility appointments'}), 403

    facility = HealthFacility.query.get(facility_id)
    if not facility:
        return jsonify({'error': 'Facility not found'}), 404

    data = request.get_json() or {}
    scheduled_time_raw = data.get('scheduled_time')
    if not scheduled_time_raw:
        return jsonify({'error': 'scheduled_time is required'}), 400

    try:
        scheduled_time = datetime.fromisoformat(str(scheduled_time_raw).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return jsonify({'error': 'scheduled_time must be a valid ISO 8601 datetime'}), 400
    minimum_time_error = _validate_minimum_schedule_time(scheduled_time)
    if minimum_time_error:
        return minimum_time_error

    mother_profile = Mother.query.filter_by(user_id=user.id).first()
    mother_name = None
    if mother_profile and mother_profile.mother_name:
        mother_name = mother_profile.mother_name
    elif isinstance(user, User):
        mother_name = user.name or f"{user.first_name} {user.last_name}".strip()

    appointment = FacilityAppointment(
        facility_id=facility_id,
        mother_id=user.id,
        mother_name=(mother_name or 'Mother').strip(),
        scheduled_time=scheduled_time,
        appointment_type=(data.get('appointment_type') or '').strip() or 'prenatal_checkup',
        status='scheduled',
        created_by_account_id=None,
        notes=(data.get('notes') or '').strip() or None,
        ticket_code=_create_facility_appointment_ticket_code(),
        ticket_status='active',
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    db.session.add(appointment)
    db.session.flush()
    _log_facility_ticket_event(
        appointment,
        'generated',
        actor_user_id=user.id,
        actor_role=user.role,
        metadata={'scheduled_time': appointment.scheduled_time.isoformat() if appointment.scheduled_time else None}
    )
    db.session.commit()

    payload = _serialize_mother_facility_appointment(appointment)

    # Facility room receives live booking updates.
    socketio.emit('facility:appointment_created', payload, to=f'facility:{facility_id}')
    _notify_facility_dashboard_on_mother_booking(appointment)

    return jsonify({'message': 'Facility appointment booked', 'appointment': payload}), 201


@bp.route('/health-facilities/appointments/mine', methods=['GET'])
@require_auth
def list_my_facility_appointments():
    """List facility appointments created for the authenticated mother."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    if user.role != 'mother':
        return jsonify({'error': 'Only mothers can view this resource'}), 403

    rows = FacilityAppointment.query.filter_by(mother_id=user.id).order_by(FacilityAppointment.scheduled_time.asc()).all()
    appointments = []

    for row in rows:
        appointments.append(_serialize_mother_facility_appointment(row))

    return jsonify({'count': len(appointments), 'appointments': appointments}), 200


@bp.route('/health-facilities/appointments/<int:appointment_id>', methods=['PATCH'])
@require_auth
def update_my_facility_appointment(appointment_id):
    """Allow a mother to confirm, decline, or comment on a facility appointment."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    if user.role != 'mother':
        return jsonify({'error': 'Only mothers can update this resource'}), 403

    appointment = FacilityAppointment.query.get(appointment_id)
    if not appointment or appointment.mother_id != user.id:
        return jsonify({'error': 'Facility appointment not found'}), 404

    if appointment.status == 'completed':
        return jsonify({'error': 'Completed facility appointments cannot be responded to'}), 400
    if appointment.status == 'canceled':
        return jsonify({'error': 'Canceled facility appointments cannot be responded to. Restore the booking first.'}), 400

    data = request.get_json() or {}
    requested_status = (data.get('response_status') or '').strip().lower() or None
    response_note = (data.get('response_note') or '').strip() or None

    if requested_status and requested_status not in {'confirmed', 'declined'}:
        return jsonify({'error': 'response_status must be confirmed or declined'}), 400
    if not requested_status and response_note is None:
        return jsonify({'error': 'response_status or response_note is required'}), 400

    if any(key in data for key in ('scheduled_time', 'appointment_type', 'notes')):
        return jsonify({'error': 'Mothers cannot edit facility appointment details after they are sent'}), 403

    previous_status = appointment.status
    appointment.mother_response_status = requested_status or appointment.mother_response_status
    appointment.mother_response_note = response_note
    appointment.mother_responded_at = datetime.now(timezone.utc)

    if requested_status == 'declined':
        appointment.status = 'canceled'
        _apply_facility_ticket_state_for_status(appointment, 'canceled')
        _log_facility_ticket_event(
            appointment,
            'canceled',
            actor_user_id=user.id,
            actor_role=user.role,
            metadata={'previous_status': previous_status, 'new_status': 'canceled', 'response_status': 'declined'},
            notes=response_note,
        )

    appointment.updated_at = datetime.now(timezone.utc)

    db.session.commit()

    _emit_facility_appointment_to_facility_room('facility:appointment_updated', appointment)
    _notify_facility_about_mother_response(appointment)

    return jsonify({
        'message': 'Facility appointment response saved',
        'appointment': _serialize_mother_facility_appointment(appointment),
    }), 200


@bp.route('/health-facilities/appointments/<int:appointment_id>', methods=['DELETE'])
@require_auth
def cancel_my_facility_appointment(appointment_id):
    """Allow a mother to cancel her own facility booking."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    if user.role != 'mother':
        return jsonify({'error': 'Only mothers can update this resource'}), 403

    appointment = FacilityAppointment.query.get(appointment_id)
    if not appointment or appointment.mother_id != user.id:
        return jsonify({'error': 'Facility appointment not found'}), 404

    if appointment.status == 'completed':
        return jsonify({'error': 'Completed facility appointments cannot be canceled'}), 400
    if appointment.status == 'canceled':
        return jsonify({'error': 'Facility appointment is already canceled'}), 400

    previous_status = appointment.status
    appointment.status = 'canceled'
    appointment.updated_at = datetime.now(timezone.utc)
    _apply_facility_ticket_state_for_status(appointment, 'canceled')
    _log_facility_ticket_event(
        appointment,
        'canceled',
        actor_user_id=user.id,
        actor_role=user.role,
        metadata={'previous_status': previous_status, 'new_status': 'canceled'},
    )
    db.session.commit()

    _emit_facility_appointment_to_facility_room('facility:appointment_updated', appointment)

    return jsonify({
        'message': 'Facility appointment canceled',
        'appointment': _serialize_mother_facility_appointment(appointment),
    }), 200


@bp.route('/health-facilities/appointments/<int:appointment_id>/restore', methods=['POST'])
@require_auth
def restore_my_facility_appointment(appointment_id):
    """Allow a mother to restore a canceled facility booking."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    if user.role != 'mother':
        return jsonify({'error': 'Only mothers can update this resource'}), 403

    appointment = FacilityAppointment.query.get(appointment_id)
    if not appointment or appointment.mother_id != user.id:
        return jsonify({'error': 'Facility appointment not found'}), 404

    if appointment.status != 'canceled':
        return jsonify({'error': 'Only canceled facility appointments can be restored'}), 400

    minimum_time_error = _validate_minimum_schedule_time(appointment.scheduled_time)
    if minimum_time_error:
        return minimum_time_error

    appointment.status = 'scheduled'
    appointment.updated_at = datetime.now(timezone.utc)
    _apply_facility_ticket_state_for_status(appointment, 'scheduled')
    _log_facility_ticket_event(
        appointment,
        'rescheduled',
        actor_user_id=user.id,
        actor_role=user.role,
        metadata={'previous_status': 'canceled', 'new_status': 'scheduled'},
    )
    db.session.commit()

    _emit_facility_appointment_to_facility_room('facility:appointment_updated', appointment)

    return jsonify({
        'message': 'Facility appointment restored',
        'appointment': _serialize_mother_facility_appointment(appointment),
    }), 200


# ============================================================
# FACILITY ISSUE REPORTING
# ============================================================

@bp.route('/health-facilities/<int:facility_id>/issues', methods=['POST'])
@require_auth
def report_facility_issue(facility_id):
    """
    Report an issue with a facility
    
    Body:
        issue_type: closed | wrong_location | wrong_name | wrong_info | other
        description: Text description of the issue
    """
    user = get_current_user()
    
    # Verify facility exists
    facility = HealthFacility.query.get(facility_id)
    if not facility:
        return jsonify({'error': 'Facility not found'}), 404
    
    data = request.get_json()
    issue_type = data.get('issue_type')
    description = data.get('description', '')
    
    # Validate issue type
    valid_types = ['closed', 'wrong_location', 'wrong_name', 'wrong_info', 'other']
    if not issue_type or issue_type not in valid_types:
        return jsonify({
            'error': 'Invalid issue_type',
            'valid_types': valid_types
        }), 400
    
    # Create issue
    issue = FacilityIssue(
        facility_id=facility_id,
        reported_by=user.id,
        issue_type=issue_type,
        description=description,
        status='reported',
        priority='medium',
        created_at=datetime.now(timezone.utc)
    )
    
    db.session.add(issue)
    db.session.commit()
    
    return jsonify({
        'message': 'Issue reported successfully',
        'issue': issue.to_dict()
    }), 201


@bp.route('/health-facilities/issues/recent', methods=['GET'])
@require_auth
def get_recent_issues():
    """
    Get recent facility issues (for admin/monitoring)

    Query params:
        status: Filter by status (reported, acknowledged, resolved)
        facility_id: Filter by specific facility
        limit: Max results (default 20, max 100)

    Authorization:
        - Admins can see all issues
        - Facility staff can only see issues for their own facility
        - Mothers/CHWs/Nurses cannot access this endpoint
    """
    user = get_current_user()

    # Authorization check: only admins and facility staff can view issues
    if user.role not in ['admin', 'facility_staff']:
        return jsonify({'error': 'Forbidden: Only admins and facility staff can view issues'}), 403

    status = request.args.get('status')
    facility_id_param = request.args.get('facility_id')
    limit = min(int(request.args.get('limit', 20)), 100)

    # Build query
    query = FacilityIssue.query

    # If facility staff, restrict to their facility
    if user.role == 'facility_staff':
        if not hasattr(user, 'facility_id') or not user.facility_id:
            return jsonify({'error': 'Facility staff must be assigned to a facility'}), 403

        # If facility_id parameter provided, verify it matches user's facility
        if facility_id_param:
            if int(facility_id_param) != user.facility_id:
                return jsonify({'error': 'Forbidden: Cannot view issues from other facilities'}), 403
            query = query.filter_by(facility_id=user.facility_id)
        else:
            # Default to their own facility
            query = query.filter_by(facility_id=user.facility_id)
    else:
        # Admins can filter by facility if specified
        if facility_id_param:
            query = query.filter_by(facility_id=int(facility_id_param))

    if status:
        query = query.filter_by(status=status)

    # Order by most recent
    query = query.order_by(FacilityIssue.created_at.desc())

    issues = query.limit(limit).all()

    return jsonify({
        'count': len(issues),
        'issues': [issue.to_dict() for issue in issues]
    }), 200


@bp.route('/health-facilities/location-review', methods=['GET'])
@require_auth
def get_location_review_queue():
    """
    Review queue for facilities whose saved boundary match is not a ward-level match.
    """
    user = get_current_user()
    if user.role != 'admin':
        return jsonify({'error': 'Forbidden: Only admins can review facility location matches'}), 403

    status = (request.args.get('status') or '').strip()
    limit = min(max(int(request.args.get('limit', 100)), 1), 500)

    query = HealthFacility.query.filter(
        or_(
            HealthFacility.location_match_status.is_(None),
            HealthFacility.location_match_status != 'matched_ward',
        )
    )
    if status:
        query = query.filter(HealthFacility.location_match_status == status)

    facilities = query.order_by(
        HealthFacility.location_match_status.asc(),
        HealthFacility.name.asc(),
    ).limit(limit).all()

    return jsonify({
        'count': len(facilities),
        'facilities': [facility.to_dict() for facility in facilities],
    }), 200


@bp.route('/health-facilities/issues/<int:issue_id>', methods=['GET'])
@require_auth
def get_issue_details(issue_id):
    """Get details of a specific issue"""
    issue = FacilityIssue.query.get(issue_id)
    
    if not issue:
        return jsonify({'error': 'Issue not found'}), 404
    
    return jsonify(issue.to_dict()), 200


# ============================================================
# STATISTICS & ANALYTICS
# ============================================================

@bp.route('/health-facilities/stats', methods=['GET'])
@require_auth
def get_facility_stats():
    """
    Get overall facility statistics
    """
    total = HealthFacility.query.count()
    verified = HealthFacility.query.filter_by(verified=True).count()
    
    # Count by amenity type
    amenity_counts = db.session.query(
        HealthFacility.amenity,
        func.count(HealthFacility.id)
    ).group_by(HealthFacility.amenity).all()
    
    # Count by operator type
    operator_counts = db.session.query(
        HealthFacility.operator_type,
        func.count(HealthFacility.id)
    ).group_by(HealthFacility.operator_type).all()
    
    # Count by city (top 10)
    city_counts = db.session.query(
        HealthFacility.city,
        func.count(HealthFacility.id)
    ).filter(HealthFacility.city.isnot(None)).group_by(
        HealthFacility.city
    ).order_by(func.count(HealthFacility.id).desc()).limit(10).all()
    
    return jsonify({
        'total_facilities': total,
        'verified_facilities': verified,
        'by_amenity': {amenity or 'unknown': count for amenity, count in amenity_counts},
        'by_operator': {operator or 'unknown': count for operator, count in operator_counts},
        'top_cities': [{'city': city, 'count': count} for city, count in city_counts]
    }), 200


@bp.route('/health-facilities/by-ward/<int:ward_id>', methods=['GET'])
def get_facilities_by_ward(ward_id):
    """
    Get facilities near a specific ward (within 20km radius)
    
    This endpoint helps CHWs find facilities in their service area.
    Returns hospitals and clinics that can serve as referral points.
    
    Query params:
        amenity: Filter by amenity type (default: hospital,clinic)
        limit: Max results (default 20, max 50)
        relevance_profile: maternal_referral|all (default maternal_referral)
    """
    try:
        from models import Ward
        
        # Get ward details
        ward = Ward.query.get(ward_id)
        if not ward:
            return jsonify({'error': 'Ward not found'}), 404
        
        amenity_values = _normalize_csv_values(request.args.get('amenity'), default_values=['hospital', 'clinic'])
        relevance_profile = _resolve_relevance_profile(request.args.get('relevance_profile'), amenity_values)

        limit_raw = (request.args.get('limit') or '20').strip()
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            return jsonify({'error': 'limit must be an integer'}), 400

        if limit < 1:
            return jsonify({'error': 'limit must be >= 1'}), 400

        limit = min(limit, 50)
        
        # Get sub-county name to help with location matching
        sub_county_name = ward.sub_county.name if ward.sub_county else None
        
        # Query facilities - prioritize those in the same city/area
        # Filter by amenity (hospitals and clinics are most relevant for CHW referrals)
        query = HealthFacility.query.filter(
            HealthFacility.amenity.in_(amenity_values)
        )

        query = query.filter(HealthFacility.name.isnot(None)).filter(func.length(func.trim(HealthFacility.name)) > 0)
        query = _apply_relevance_profile(query, relevance_profile)
        
        def _ordered_facilities(filtered_query):
            return (
                filtered_query.order_by(
                    HealthFacility.verified.desc(),
                    func.coalesce(HealthFacility.inference_confidence, 0).desc(),
                    HealthFacility.name
                ).limit(limit).all()
            )

        # Start with ward matches, then fill the remainder from the same sub-county so
        # CHWs can link to facilities outside their ward but still within the selected sub-county.
        ward_facilities = _ordered_facilities(query.filter(
            HealthFacility.inferred_ward_id == ward.id
        ))

        matched_by = 'inferred_ward'
        facilities = list(ward_facilities)
        seen_ids = {facility.id for facility in facilities}

        if len(facilities) < limit:
            subcounty_facilities = _ordered_facilities(query.filter(
                HealthFacility.inferred_sub_county_id == ward.sub_county_id
            ))
            for facility in subcounty_facilities:
                if facility.id in seen_ids:
                    continue
                facilities.append(facility)
                seen_ids.add(facility.id)
                if len(facilities) >= limit:
                    break
            if facilities and len(facilities) > len(ward_facilities):
                matched_by = 'inferred_subcounty'

        if not facilities:
            matched_by = 'text_fallback'
            if sub_county_name:
                query = query.filter(
                    or_(
                        HealthFacility.city.ilike(f'%{sub_county_name}%'),
                        HealthFacility.city.ilike(f'%Nairobi%')  # Fallback to Nairobi facilities
                    )
                )

            # Order by verified status first, then by name
            query = query.order_by(
                HealthFacility.verified.desc(),
                HealthFacility.name
            )

            facilities = query.limit(limit).all()
        
        return jsonify({
            'ward': {
                'id': ward.id,
                'name': ward.name,
                'sub_county': sub_county_name
            },
            'filter_profile': relevance_profile,
            'matched_by': matched_by,
            'facilities': [_serialize_ward_linked_facility(f, matched_by) for f in facilities],
            'count': len(facilities)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
