import logging
import os
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy import text

from app import db

log = logging.getLogger(__name__)


class AfricasTalkingOTPService:
    """OTP delivery service using Africa's Talking."""

    def __init__(self) -> None:
        self.enabled = os.getenv("OTP_DELIVERY_ENABLED", "true").strip().lower() == "true"
        self.sandbox_mode = os.getenv("OTP_SANDBOX_MODE", "true").strip().lower() == "true"
        self.delivery_method = os.getenv("OTP_DELIVERY_METHOD", "sms").strip().lower()

        api_key = os.getenv("AFRICAS_TALKING_API_KEY")
        username = os.getenv("AFRICAS_TALKING_USERNAME", "sandbox" if self.sandbox_mode else "")
        sender_id = os.getenv("AFRICAS_TALKING_SENDER_ID", "RemyAfya")
        shortcode = os.getenv("AFRICAS_TALKING_SHORTCODE", "20880")

        self.api_key = api_key.strip() if api_key else None
        self.username = username.strip() if username else None
        self.sender_id = sender_id.strip() if sender_id else None
        self.shortcode = shortcode.strip() if shortcode else "20880"

        self.sms = None
        self._sdk_available = False
        if self.enabled and self.api_key and self.username:
            try:
                import africastalking
                africastalking.initialize(username=self.username, api_key=self.api_key)
                self.sms = africastalking.SMS
                self._sdk_available = True
                mode = "SANDBOX" if self.sandbox_mode else "PRODUCTION"
                if self.sandbox_mode and self.username != "sandbox":
                    log.warning("[AT] Sandbox mode is on but username is '%s' (expected 'sandbox')", self.username)
                log.info("[AT] Initialized OTP delivery service in %s mode", mode)
            except ModuleNotFoundError:
                log.warning("[AT] africastalking SDK not installed; using console fallback")
                self.sms = None
            except Exception as exc:
                log.error("[AT] Failed to initialize Africa's Talking SDK: %s", exc)
                self.sms = None
        elif self.enabled:
            log.warning("[AT] OTP delivery enabled but credentials are missing; using console fallback")

    def send_otp_sms(self, phone_number: str, otp_code: str) -> Tuple[bool, str, str]:
        if not self.enabled:
            print(f"[DEV] OTP for {phone_number}: {otp_code}")
            return True, "OTP delivery disabled (console mode)", "console"

        if self.sms is None:
            print(f"[DEV] OTP for {phone_number}: {otp_code}")
            return True, "SMS client unavailable (console fallback)", "console"

        message = f"Your RemyAfya OTP is: {otp_code}. Valid for 10 minutes."
        try:
            kwargs = {
                "message": message,
                "recipients": [phone_number],
            }
            if self.sender_id and not self.sandbox_mode:
                kwargs["sender_id"] = self.sender_id

            response = self.sms.send(**kwargs)
            recipients = response.get("SMSMessageData", {}).get("Recipients", [])
            if recipients:
                status = str(recipients[0].get("status", "")).lower()
                if status in {"success", "sent", "queued"}:
                    return True, "SMS sent successfully", "sms"
            return False, f"SMS send failed: {response}", "sms"
        except Exception as exc:
            return False, f"SMS error: {exc}", "sms"

    def send_otp_whatsapp(self, phone_number: str, otp_code: str) -> Tuple[bool, str, str]:
        log.info("[AT] WhatsApp delivery not implemented; falling back to SMS for %s", phone_number)
        return self.send_otp_sms(phone_number, otp_code)

    def send_otp(self, phone_number: str, otp_code: str) -> Tuple[bool, str, str]:
        if not phone_number or not otp_code:
            return False, "Invalid phone or OTP", "sms"

        if self.delivery_method == "whatsapp":
            return self.send_otp_whatsapp(phone_number, otp_code)
        if self.delivery_method == "auto":
            success, msg, method = self.send_otp_whatsapp(phone_number, otp_code)
            if success:
                return success, msg, method
            return self.send_otp_sms(phone_number, otp_code)
        return self.send_otp_sms(phone_number, otp_code)

    def log_otp_delivery(
        self,
        phone_number: str,
        success: bool,
        method: str,
        error: Optional[str] = None,
    ) -> None:
        try:
            db.session.execute(
                text(
                    """
                    INSERT INTO otp_delivery_logs (phone_number, method, success, error_message, created_at)
                    VALUES (:phone_number, :method, :success, :error_message, :created_at)
                    """
                ),
                {
                    "phone_number": phone_number,
                    "method": method,
                    "success": success,
                    "error_message": error,
                    "created_at": datetime.now(timezone.utc),
                },
            )
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            log.warning("[AT] Failed to log OTP delivery for %s: %s", phone_number, exc)


_otp_service: Optional[AfricasTalkingOTPService] = None


def get_otp_service() -> AfricasTalkingOTPService:
    global _otp_service
    if _otp_service is None:
        _otp_service = AfricasTalkingOTPService()
    return _otp_service


def send_otp(phone_number: str, otp_code: str) -> Tuple[bool, str, str]:
    return get_otp_service().send_otp(phone_number, otp_code)

