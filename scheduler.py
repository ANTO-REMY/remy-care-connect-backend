import logging
from datetime import datetime, timezone
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from app import db # Need active app context though
from models import Reminder, User
from notifications import send_push, create_user_notification
from push_payloads import build_push_data

log = logging.getLogger(__name__)
scheduler = BackgroundScheduler()

def trigger_reminders(app):
    with app.app_context():
        # Get exact current time in HH:MM format (local time - Nairobi typically)
        local_tz = pytz.timezone('Africa/Nairobi')
        now_local = datetime.now(local_tz)
        current_time_str = now_local.strftime('%H:%M')
        today_date = now_local.date()

        # Find reminders matching exactly this time
        # We also need to check they haven't been completed today.
        reminders = Reminder.query.filter_by(time_string=current_time_str).all()

        for r in reminders:
            # Need to determine if reminder complete today
            already_done = False
            if r.last_completed_at:
                # convert last_completed_at to our local TZ to reliably compare "today"
                completed_local = r.last_completed_at.astimezone(local_tz)
                if r.frequency == 'daily' and completed_local.date() == today_date:
                    already_done = True
                elif r.frequency != 'daily':
                    already_done = True

            if not already_done:
                user = User.query.get(r.user_id)
                if user:
                    log.info(f"Triggering reminder '{r.title}' for user {user.phone_number} at {current_time_str}")
                    try:
                        # 1) Persist in-app notification first so the bell icon updates even if FCM fails.
                        create_user_notification(
                            user_id=r.user_id,
                            event_type="reminder_triggered",
                            title="Task Reminder",
                            message=f"Time to: {r.title}",
                            url="/dashboard/mother",
                            entity_type="reminder",
                            entity_id=r.id,
                            emit_socket_event=True,
                        )
                    except Exception as e:
                        db.session.rollback()
                        log.error(f"Failed to persist reminder notification for reminder {r.id}: {e}")

                    try:
                        # 2) Send FCM push best-effort using the shared payload schema.
                        send_push(
                            r.user_id,
                            "Task Reminder",
                            f"Time to: {r.title}",
                            data=build_push_data(
                                event="reminder_triggered",
                                url="/dashboard/mother",
                                entity_type="reminder",
                                entity_id=r.id,
                                role="mother",
                                extra={"icon": r.icon or "BELL"},
                            ),
                        )
                    except Exception as e:
                        db.session.rollback()
                        log.error(f"Failed to send reminder push for reminder {r.id}: {e}")

def init_scheduler(app):
    if scheduler.running:
        log.info("APScheduler already running; skipping re-initialization.")
        return

    # APScheduler should only start once in production (especially if not using gunicorn/multiple workers)
    # or you use a Lock / cache mechanism. For demo, just start it.
    
    # We pass `app` to trigger_reminders so it has an app context
    scheduler.add_job(
        func=trigger_reminders,
        trigger='cron',
        minute='*', # Runs every minute at the 00 second mark
        args=[app],
        id='reminder_job',
        replace_existing=True
    )
    
    scheduler.start()
    log.info("APScheduler initialized and started for background push notifications.")
