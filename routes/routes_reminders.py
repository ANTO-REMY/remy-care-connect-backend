from flask import Blueprint, jsonify, request
from auth_utils import require_auth, get_current_user
from models import db, Reminder, AppointmentSchedule
import datetime

bp = Blueprint('reminders', __name__)


def _normalize_time_string(value: str) -> str:
    """Convert reminder time input to canonical HH:MM 24-hour format."""
    if not value:
        raise ValueError("Time is required")

    candidate = value.strip()

    for fmt in ("%H:%M", "%I:%M %p", "%I:%M%p"):
        try:
            parsed = datetime.datetime.strptime(candidate, fmt)
            return parsed.strftime("%H:%M")
        except ValueError:
            pass

    digits = ''.join(ch for ch in candidate if ch.isdigit())
    if len(digits) == 4:
        hours = int(digits[:2])
        minutes = int(digits[2:])
    elif len(digits) == 3:
        hours = int(digits[:1])
        minutes = int(digits[1:])
    else:
        raise ValueError("Time must be in HH:MM (24-hour) format")

    if hours > 23 or minutes > 59:
        raise ValueError("Time must be in HH:MM (24-hour) format")

    return f"{hours:02d}:{minutes:02d}"

@bp.route('/reminders', methods=['GET'])
@require_auth
def get_reminders():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Authentication required."}), 401

    if user.role != 'mother':
        return jsonify({"error": "Only mothers can view their reminders here."}), 403

    reminders = Reminder.query.filter_by(user_id=user.id).order_by(Reminder.created_at.asc()).all()
    
    # We also want to merge in today's appointments as dynamic reminders
    import datetime
    today = datetime.datetime.utcnow().date()
    # Find appointments happening today
    appts = AppointmentSchedule.query.filter(
        AppointmentSchedule.mother_id == user.id,
        db.func.date(AppointmentSchedule.scheduled_time) == today,
        AppointmentSchedule.status == 'scheduled'
    ).all()

    result_reminders = []
    now = datetime.datetime.now(datetime.timezone.utc)
    for r in reminders:
        # Compute if it's completed today
        is_completed = False
        if r.last_completed_at:
            # If frequency is daily, must be completed today.
            # If once, it's just completed if not null.
            if r.frequency == 'daily':
                # Convert to local time approximation or use UTC date.
                if r.last_completed_at.date() == now.date():
                    is_completed = True
            else:
                is_completed = True
                
        result_reminders.append({
            "id": r.id,
            "title": r.title,
            "time": r.time_string,
            "completed": is_completed,
            "type": r.type,
            "icon": r.icon,
            # We add a unique string ID to differentiate from appointments in UI if needed
            "internal_id": f"rem_{r.id}"
        })

    # Merge modern appointments as reminders
    for a in appts:
        result_reminders.append({
            "id": f"appt_{a.id}", # use string id for appts
            "title": f"{a.appointment_type.replace('_', ' ').title()}",
            "time": a.scheduled_time.strftime("%I:%M %p"),
            "completed": False, 
            "type": "appointment",
            "icon": "CAL",
            "internal_id": f"appt_{a.id}"
        })

    return jsonify({"reminders": result_reminders}), 200

@bp.route('/reminders', methods=['POST'])
@require_auth
def create_reminder():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Authentication required."}), 401

    data = request.get_json() or {}
    
    # Simple validation
    if not data.get('title') or not data.get('time'):
        return jsonify({"error": "Title and time are required."}), 400

    # Determine who owns this reminder
    # If a CHW/Nurse creates it, they send `user_id` in body
    mother_id = user.id
    creator_id = user.id
    if user.role != 'mother':
        mother_id = data.get('user_id')
        if not mother_id:
            return jsonify({"error": "Must provide user_id to assign reminder to."}), 400

    try:
        normalized_time = _normalize_time_string(str(data['time']))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    reminder = Reminder(
        user_id=mother_id,
        created_by_user_id=creator_id if creator_id != mother_id else None,
        title=data['title'],
        type=data.get('type', 'custom'),
        time_string=normalized_time,
        frequency=data.get('frequency', 'daily'),
        icon=data.get('icon', 'BELL')
    )

    db.session.add(reminder)
    db.session.commit()

    # Emit socket event to the mother
    from socket_manager import socketio
    socketio.emit("reminder:created", {"message": "New reminder added"}, to=f"user:{mother_id}")

    return jsonify({"message": "Reminder created successfully", "id": reminder.id}), 201

@bp.route('/reminders/<int:reminder_id>/toggle', methods=['PATCH'])
@require_auth
def toggle_reminder(reminder_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Authentication required."}), 401

    reminder = Reminder.query.get(reminder_id)
    if not reminder or reminder.user_id != user.id:
        return jsonify({"error": "Reminder not found or unauthorized."}), 404

    # Toggle logic
    now = datetime.datetime.now(datetime.timezone.utc)
    is_completed = False
    if reminder.last_completed_at:
        if reminder.frequency == 'daily':
            if reminder.last_completed_at.date() == now.date():
                # Already completed today, so we UN-complete it
                reminder.last_completed_at = None
            else:
                # Completed a previous day, so completing it for today
                reminder.last_completed_at = now
                is_completed = True
        else:
            # Frequency 'once', it was completed, now we UN-complete
            reminder.last_completed_at = None
    else:
        # Was not completed, now completing
        reminder.last_completed_at = now
        is_completed = True

    db.session.commit()

    # Emit socket event
    from socket_manager import socketio
    socketio.emit("reminder:updated", {"id": reminder.id}, to=f"user:{user.id}")

    return jsonify({"message": "Reminder toggled", "completed": is_completed}), 200

@bp.route('/reminders/<int:reminder_id>', methods=['PUT'])
@require_auth
def update_reminder(reminder_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Authentication required."}), 401

    reminder = Reminder.query.get(reminder_id)
    if not reminder or reminder.user_id != user.id:
        return jsonify({"error": "Reminder not found or unauthorized."}), 404

    data = request.get_json() or {}
    
    if 'title' in data:
        reminder.title = data['title']
    if 'time' in data:
        try:
            reminder.time_string = _normalize_time_string(str(data['time']))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    db.session.commit()

    from socket_manager import socketio
    socketio.emit("reminder:updated", {"id": reminder.id}, to=f"user:{user.id}")

    return jsonify({"message": "Reminder updated successfully"}), 200

@bp.route('/reminders/<int:reminder_id>', methods=['DELETE'])
@require_auth
def delete_reminder(reminder_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Authentication required."}), 401

    reminder = Reminder.query.get(reminder_id)
    if not reminder or reminder.user_id != user.id:
        return jsonify({"error": "Reminder not found or unauthorized."}), 404

    db.session.delete(reminder)
    db.session.commit()

    # Emit socket event
    from socket_manager import socketio
    socketio.emit("reminder:deleted", {"id": reminder_id}, to=f"user:{user.id}")

    return jsonify({"message": "Reminder deleted successfully"}), 200
