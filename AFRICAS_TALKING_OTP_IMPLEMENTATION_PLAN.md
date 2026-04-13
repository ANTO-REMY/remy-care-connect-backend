# Africa's Talking OTP Delivery Integration - Implementation Plan

**Status:** Ready for Implementation (Sandbox Phase)  
**Framework:** Flask 3.0.3 + SQLAlchemy  
**Database:** PostgreSQL  
**Integration Type:** SMS/WhatsApp OTP Delivery  
**Phase:** Sandbox (→ Production after validation)

---

## Executive Summary

Currently, the RemyAfya backend generates OTPs and prints them to console for development. This plan integrates **Africa's Talking API** to deliver OTPs via SMS/WhatsApp in sandbox mode, then production.

**Key Points:**
- OTP table already exists (schema ready)
- OTP generation already implemented
- SMS delivery is the missing piece (this plan)
- No breaking changes to existing code
- Fallback to console logging for dev/test environments
- Full logging and error handling

---

## Architecture Overview

```
User Registration Flow:
├─ 1. User submits: phone_number, name, PIN, role
├─ 2. Backend generates OTP (5-digit)
├─ 3. OTP stored in database (Verification table)
├─ 4. [NEW] OTP sent via Africa's Talking SMS/WhatsApp
├─ 5. User receives: "Your RemyAfya OTP is: 12345"
├─ 6. User submits phone + OTP code
├─ 7. Backend verifies OTP
└─ 8. User is verified → profile created

Africa's Talking Integration Points:
├─ SMS API (Primary - more reliable)
├─ WhatsApp API (Secondary - better UX)
├─ Sandbox credentials (testing)
└─ Production API key (when ready)
```

---

## Implementation Steps

### PHASE 1: Setup & Configuration (Day 1)

#### Step 1.1: Add Africa's Talking Dependencies
**File:** `requirements.txt`

Add the Africa's Talking Python SDK:
```
requests>=2.31.0
africastalking>=1.2.4
```

**Action:**
```bash
pip install requests africastalking
```

#### Step 1.2: Update Environment Configuration
**File:** `.env.example`

Add new environment variables:
```env
# Africa's Talking Configuration
AFRICAS_TALKING_API_KEY=your-sandbox-api-key-here
AFRICAS_TALKING_USERNAME=RemyAfya  # Or your AT username
AFRICAS_TALKING_SHORTCODE=20880    # Your SMS shortcode (sandbox default or your actual)
AFRICAS_TALKING_SENDER_ID=RemyAfya # Sender ID for SMS messages

# Feature Flags
OTP_DELIVERY_METHOD=sms  # 'sms', 'whatsapp', 'auto' (try WhatsApp then SMS)
OTP_DELIVERY_ENABLED=true  # Set false to disable (fallback to console)
OTP_SANDBOX_MODE=true  # Set false for production

# Logging
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
```

**Action in actual `.env`:**
```env
# Existing vars...

# Africa's Talking OTP Delivery
AFRICAS_TALKING_API_KEY=5c123456789abcdef123456789abcdef  # Your actual sandbox key
AFRICAS_TALKING_USERNAME=RemyAfya  # Your AT username (given to you)
AFRICAS_TALKING_SHORTCODE=20880

OTP_DELIVERY_METHOD=sms
OTP_DELIVERY_ENABLED=true
OTP_SANDBOX_MODE=true
LOG_LEVEL=INFO
```

**Notes:**
- Get API key from: https://africastalking.com/app/settings/api (sandbox section)
- Default sandbox shortcode: **20880**
- Production: Get your own shortcode from AT
- Keep API key secret (add to `.env, .gitignore`)

#### Step 1.3: Create Africa's Talking Service Module
**File to Create:** `/africas_talking_service.py`

```python
"""
africas_talking_service.py
────────────────────────────
Africa's Talking SMS/WhatsApp OTP delivery service.

Handles:
- OTP delivery via SMS or WhatsApp
- Error handling and retries
- Sandbox vs production mode
- Logging and monitoring
- Fallback to console for dev environments
"""

import os
import logging
import africastalking
from typing import Tuple, Optional
from datetime import datetime, timezone

log = logging.getLogger(__name__)

class AfricasTalkingOTPService:
    """Service for sending OTPs via Africa's Talking"""
    
    def __init__(self):
        """Initialize Africa's Talking SDK with credentials from environment"""
        self.api_key = os.getenv('AFRICAS_TALKING_API_KEY')
        self.username = os.getenv('AFRICAS_TALKING_USERNAME', 'RemyAfya')
        self.shortcode = os.getenv('AFRICAS_TALKING_SHORTCODE', '20880')
        self.sender_id = os.getenv('AFRICAS_TALKING_SENDER_ID', 'RemyAfya')
        
        # Feature flags
        self.enabled = os.getenv('OTP_DELIVERY_ENABLED', 'true').lower() == 'true'
        self.sandbox_mode = os.getenv('OTP_SANDBOX_MODE', 'true').lower() == 'true'
        self.delivery_method = os.getenv('OTP_DELIVERY_METHOD', 'sms')  # 'sms', 'whatsapp', 'auto'
        
        # Initialize Africa's Talking
        self.client = None
        self.sms = None
        if self.enabled and self.api_key and self.username:
            try:
                africastalking.initialize(
                    username=self.username,
                    api_key=self.api_key,
                    environment='sandbox' if self.sandbox_mode else 'production'
                )
                self.sms = africastalking.SMS
                log.info(f"[AT] Initialized in {'SANDBOX' if self.sandbox_mode else 'PRODUCTION'} mode")
            except Exception as e:
                log.error(f"[AT] Failed to initialize: {e}")
                self.sms = None
    
    def send_otp_sms(self, phone_number: str, otp_code: str) -> Tuple[bool, str]:
        """
        Send OTP via SMS
        
        Args:
            phone_number: Recipient phone (e.g. +254712345678)
            otp_code: 5-digit OTP code
        
        Returns:
            (success: bool, message: str)
        """
        if not self.enabled:
            log.info(f"[AT] OTP delivery disabled. OTP for {phone_number}: {otp_code}")
            return True, "Development mode (console)"
        
        if not self.sms:
            log.warning("[AT] SMS client not initialized, falling back to console")
            print(f"[DEV] OTP for {phone_number}: {otp_code}")
            return True, "SMS client unavailable (console fallback)"
        
        try:
            # Format message
            message = f"Your RemyAfya OTP is: {otp_code}. Valid for 10 minutes."
            
            # Send via Africa's Talking
            response = self.sms.send(
                message=message,
                recipients=[phone_number],
                sender_id=self.sender_id if not self.sandbox_mode else None
            )
            
            # Parse response
            if response['SMSMessageData']['Message'] == 'Sent':
                log.info(f"[AT-SMS] OTP sent to {phone_number}")
                return True, "SMS sent successfully"
            else:
                error_msg = response['SMSMessageData'].get('Message', 'Unknown error')
                log.warning(f"[AT-SMS] Failed to send to {phone_number}: {error_msg}")
                return False, f"SMS error: {error_msg}"
                
        except Exception as e:
            log.error(f"[AT-SMS] Exception sending to {phone_number}: {e}")
            return False, f"SMS error: {str(e)}"
    
    def send_otp_whatsapp(self, phone_number: str, otp_code: str) -> Tuple[bool, str]:
        """
        Send OTP via WhatsApp
        
        Note: WhatsApp requires special setup with Africa's Talking.
        For now, returns not implemented.
        
        Args:
            phone_number: Recipient phone (e.g. +254712345678)
            otp_code: 5-digit OTP code
        
        Returns:
            (success: bool, message: str)
        """
        log.info(f"[AT-WA] WhatsApp OTP not yet implemented for {phone_number}")
        return False, "WhatsApp OTP not implemented"
    
    def send_otp(self, phone_number: str, otp_code: str) -> Tuple[bool, str]:
        """
        Send OTP using configured delivery method
        
        Args:
            phone_number: Recipient phone number
            otp_code: 5-digit OTP code
        
        Returns:
            (success: bool, message: str)
        """
        if not phone_number or not otp_code:
            return False, "Invalid phone or OTP"
        
        # Handle delivery method
        if self.delivery_method == 'sms':
            return self.send_otp_sms(phone_number, otp_code)
        
        elif self.delivery_method == 'whatsapp':
            return self.send_otp_whatsapp(phone_number, otp_code)
        
        elif self.delivery_method == 'auto':
            # Try WhatsApp first, fall back to SMS
            success, msg = self.send_otp_whatsapp(phone_number, otp_code)
            if not success:
                log.info("[AT] WhatsApp failed, falling back to SMS")
                return self.send_otp_sms(phone_number, otp_code)
            return success, msg
        
        else:
            # Default to SMS
            return self.send_otp_sms(phone_number, otp_code)
    
    def log_otp_delivery(self, phone_number: str, otp_code: str, success: bool, method: str, error: Optional[str] = None):
        """Log OTP delivery attempts for audit trail"""
        from app import db
        from datetime import datetime, timezone
        
        try:
            db.session.execute(
                db.text("""
                    INSERT INTO otp_delivery_logs 
                    (phone_number, method, success, error_message, created_at)
                    VALUES (:phone, :method, :success, :error, :created_at)
                """),
                {
                    'phone': phone_number,
                    'method': method,
                    'success': success,
                    'error': error,
                    'created_at': datetime.now(timezone.utc)
                }
            )
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            log.debug(f"[AT] Could not log OTP delivery: {e}")


# Singleton instance
_otp_service = None

def get_otp_service() -> AfricasTalkingOTPService:
    """Get or initialize the OTP service singleton"""
    global _otp_service
    if _otp_service is None:
        _otp_service = AfricasTalkingOTPService()
    return _otp_service


def send_otp(phone_number: str, otp_code: str) -> Tuple[bool, str]:
    """Convenience function to send OTP"""
    service = get_otp_service()
    return service.send_otp(phone_number, otp_code)
```

**Key Features:**
- Initialization with environment variables
- SMS delivery via Africa's Talking API
- WhatsApp support (placeholder for future)
- Auto-fallback strategy
- Graceful degradation (console fallback if API unavailable)
- Comprehensive logging
- Sandbox/production mode switching

---

### PHASE 2: Database Logging (Day 1)

#### Step 2.1: Create OTP Delivery Log Table
**File to Create:** `/migrations/036_create_otp_delivery_logs.sql`

```sql
-- Create table for OTP delivery audit trail
CREATE TABLE otp_delivery_logs (
    id SERIAL PRIMARY KEY,
    phone_number VARCHAR NOT NULL,
    method VARCHAR NOT NULL CHECK (method IN ('sms', 'whatsapp', 'console')),
    success BOOLEAN NOT NULL,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Indexes for quick lookup
    INDEX idx_phone_delivery (phone_number, created_at),
    INDEX idx_success_delivery (success, created_at)
);

-- Add comment for clarity
COMMENT ON TABLE otp_delivery_logs IS 'Audit trail for OTP delivery attempts via Africa''s Talking';
COMMENT ON COLUMN otp_delivery_logs.method IS 'Delivery method: sms, whatsapp, or console (development)';
COMMENT ON COLUMN otp_delivery_logs.success IS 'Whether delivery was successful';
```

**Action:**
1. Create the migration file
2. Run migration: `python -m flask db upgrade` or execute SQL directly
3. Verify table created with `\dt otp_delivery_logs;` in psql

#### Step 2.2: Add OTP Settings Model (Optional but Recommended)
**File:** `/models.py` - Add new model:

```python
class OTPDeliveryLog(db.Model):
    """Audit trail for OTP delivery attempts"""
    __tablename__ = 'otp_delivery_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), nullable=False, index=True)
    method = db.Column(db.String(20), nullable=False)  # 'sms', 'whatsapp', 'console'
    success = db.Column(db.Boolean, nullable=False, index=True)
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.now(timezone.utc), index=True)
```

---

### PHASE 3: Integrate OTP Delivery into Auth Flow (Day 2)

#### Step 3.1: Update Registration Endpoint
**File:** `/auth.py` - Modify `@bp.route('/auth/register')`

```python
@bp.route('/auth/register', methods=['POST'])
def register():
    """Register a new user and send OTP for verification"""
    # ... existing validation code ...
    
    try:
        # Create new user (unverified)
        user = User(
            phone_number=phone_number,
            first_name=first_name,
            last_name=last_name,
            email=email,
            pin_hash=hash_pin(pin),
            role=role,
            is_verified=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        db.session.add(user)
        db.session.flush()  # Get user ID without committing
        
        # Generate and store OTP
        otp_code = generate_otp()
        verification = Verification(
            user_id=user.id,
            phone_number=phone_number,
            code=otp_code,
            status='pending',
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
        )
        
        db.session.add(verification)
        db.session.commit()
        
        # ━━━━━━━━━━━━━━━━ NEW: SEND OTP VIA AFRICA'S TALKING ━━━━━━━━━━━━━━━━
        from africas_talking_service import send_otp, get_otp_service
        
        success, msg = send_otp(phone_number, otp_code)
        service = get_otp_service()
        service.log_otp_delivery(
            phone_number=phone_number,
            otp_code=otp_code,
            success=success,
            method=service.delivery_method,
            error=None if success else msg
        )
        
        if not success:
            log.warning(f"[OTP] Failed to deliver OTP to {phone_number}: {msg}")
            # Don't fail registration, but log the issue. User can request resend.
        
        return jsonify({
            'message': 'Registration successful. Please verify your phone number.',
            'user_id': user.id,
            'role': role,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'expires_in': '10 minutes',
            'otp_delivery_status': 'sent' if success else 'pending_retry'  # Frontend awareness
        }), 201
        
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'Registration failed. Please try again.'}), 500
```

**Changes:**
- Import Africa's Talking service
- Send OTP after database commit
- Log delivery status
- Return delivery status to frontend
- Handle failure gracefully (don't fail registration)

#### Step 3.2: Update Resend OTP Endpoint
**File:** `/auth.py` - Modify `@bp.route('/auth/resend-otp')`

```python
@bp.route('/auth/resend-otp', methods=['POST'])
def resend_otp():
    """Resend OTP for phone verification"""
    data = request.get_json()
    phone_number = data.get('phone_number')
    
    if not phone_number:
        return jsonify({'error': 'Phone number is required'}), 400
    
    # Find unverified user
    user = User.query.filter_by(phone_number=phone_number, is_verified=False).first()
    if not user:
        return jsonify({'error': 'No unverified user found with this phone number'}), 404
    
    # Invalidate old OTPs
    old_verifications = Verification.query.filter_by(
        phone_number=phone_number,
        status='pending'
    ).all()
    
    for verification in old_verifications:
        verification.status = 'expired'
    
    # Generate new OTP
    otp_code = generate_otp()
    verification = Verification(
        user_id=user.id,
        phone_number=phone_number,
        code=otp_code,
        status='pending',
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
    )
    
    db.session.add(verification)
    db.session.commit()
    
    # ━━━━━━━━━━━━━━━━ NEW: SEND OTP VIA AFRICA'S TALKING ━━━━━━━━━━━━━━━━
    from africas_talking_service import send_otp, get_otp_service
    
    success, msg = send_otp(phone_number, otp_code)
    service = get_otp_service()
    service.log_otp_delivery(
        phone_number=phone_number,
        otp_code=otp_code,
        success=success,
        method=service.delivery_method,
        error=None if success else msg
    )
    
    if not success:
        log.warning(f"[OTP] Failed to resend OTP to {phone_number}: {msg}")
    
    return jsonify({
        'message': 'OTP resent successfully.',
        'expires_in': '10 minutes',
        'otp_delivery_status': 'sent' if success else 'failed'
    }), 200
```

---

### PHASE 4: App Initialization (Day 2)

#### Step 4.1: Initialize Africa's Talking Service at Startup
**File:** `/app.py` - Add initialization

```python
# At the top of app factory or after blueprints registration:

def create_app():
    app = Flask(__name__)
    
    # ... existing configuration ...
    
    # Register blueprints
    # ... existing blueprint registration ...
    
    # ━━━━━━━━━━━━━━━━ NEW: Initialize Africa's Talking Service ━━━━━━━━━━━━━━━━
    from africas_talking_service import get_otp_service
    
    with app.app_context():
        try:
            otp_service = get_otp_service()
            enabled = os.getenv('OTP_DELIVERY_ENABLED', 'true').lower() == 'true'
            sandbox = os.getenv('OTP_SANDBOX_MODE', 'true').lower() == 'true'
            if enabled:
                mode = "SANDBOX" if sandbox else "PRODUCTION"
                app.logger.info(f"✓ Africa's Talking OTP service initialized ({mode} mode)")
            else:
                app.logger.info("⚠ Africa's Talking OTP delivery disabled (console mode)")
        except Exception as e:
            app.logger.error(f"✗ Failed to initialize OTP service: {e}")
    
    return app
```

---

### PHASE 5: Testing & Validation (Day 2-3)

#### Step 5.1: Sandbox Testing Checklist

```
SANDBOX MODE TESTING - Africa's Talking
──────────────────────────────────────

Environment Setup:
☐ Sandbox API key set in .env (AFRICAS_TALKING_API_KEY)
☐ AT_USERNAME set to your Africa's Talking username
☐ OTP_SANDBOX_MODE=true
☐ OTP_DELIVERY_ENABLED=true

Prerequisites:
☐ Requirements.txt updated with africas_talking library
☐ requirements installed: pip install -r requirements.txt
☐ Migration 036 created and applied
☐ africas_talking_service.py created

Register Test Cases:
☐ Test 1: Normal registration flow
   1. POST /api/v1/auth/register with:
      - phone_number: 0712345678
      - first_name: John
      - last_name: Doe
      - pin: 1234
      - role: mother
      - dob: 1995-01-15
      - due_date: 2026-08-15
      - ward_id: 1
   2. Verify response contains: user_id, role, otp_delivery_status='sent'
   3. Check Africa's Talking dashboard for delivery status
   4. Check otp_delivery_logs table for entry

☐ Test 2: Resend OTP
   1. POST /api/v1/auth/resend-otp with:
      - phone_number: 0712345678
   2. Verify old OTPs marked as 'expired'
   3. Verify new OTP generated
   4. Check Africa's Talking delivery
   5. Verify otp_delivery_logs entry

☐ Test 3: OTP Verification
   1. Get OTP from otp_delivery_logs or database
   2. POST /api/v1/auth/verify-otp with:
      - phone_number: 0712345678
      - otp_code: [from OTP]
      - (mother fields if applicable)
   3. Verify user.is_verified = True
   4. Verify profile created

Error Handling:
☐ Test 4: Invalid phone number
   1. POST /auth/register with invalid phone format
   2. Verify proper error response

☐ Test 5: Duplicate registration
   1. Register with phone X
   2. Try to register again with phone X
   3. Verify 409 error

☐ Test 6: Wrong OTP
   1. Register user
   2. POST /verify-otp with wrong code
   3. Verify 400 error

☐ Test 7: Expired OTP
   1. Register user, wait 10+ minutes
   2. POST /verify-otp with original code
   3. Verify 'expired' error

Logging:
☐ Test 8: Check logs
   1. Review application logs for [AT] prefixed messages
   2. Verify otp_delivery_logs table has entries
   3. Check success/error messages

Fallback Testing:
☐ Test 9: Disable OTP delivery
   1. Set OTP_DELIVERY_ENABLED=false
   2. Register new user
   3. Verify OTP printed to console instead
   4. Verify otp_delivery_logs shows console method
```

#### Step 5.2: Database Inspection

```sql
-- Check OTP delivery logs
SELECT * FROM otp_delivery_logs ORDER BY created_at DESC LIMIT 10;

-- Check delivery rate (should be high in sandbox)
SELECT 
    method,
    COUNT(*) as total,
    SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful,
    ROUND(100.0 * SUM(CASE WHEN success THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate
FROM otp_delivery_logs
GROUP BY method;

-- Check recent Verification entries
SELECT 
    u.phone_number,
    u.first_name,
    v.code,
    v.status,
    v.created_at,
    v.expires_at
FROM verifications v
JOIN users u ON u.id = v.user_id
ORDER BY v.created_at DESC LIMIT 5;
```

---

### PHASE 6: Production Readiness (Day 3)

#### Step 6.1: Production Migration Checklist

```
PRODUCTION MIGRATION - Africa's Talking
───────────────────────────────────────

Pre-Production:
☐ Load test: 100+ concurrent registrations in sandbox
☐ Verify no duplicate OTPs
☐ Verify delivery latency < 3 seconds
☐ Verify success rate > 99% in sandbox

API Key Management:
☐ Get production API key from Africa's Talking dashboard
☐ Request production SMS shortcode (if not using default)
☐ Test with real numbers (not just sandbox test numbers)
☐ Verify rate limits with Africa's Talking support

Environment Update:
☐ Create production .env with:
   - AFRICAS_TALKING_API_KEY=<production_key>
   - AFRICAS_TALKING_USERNAME=<production_username>
   - AFRICAS_TALKING_SHORTCODE=<your_shortcode>
   - AFRICAS_TALKING_SENDER_ID=RemyAfya
   - OTP_SANDBOX_MODE=false
   - OTP_DELIVERY_ENABLED=true

Deployment:
☐ Deploy code to production
☐ Run migrations on production DB
☐ Update .env (Africa's Talking credentials)
☐ Restart application
☐ Verify startup logs: "✓ Africa's Talking OTP service initialized"

Smoke Testing:
☐ Test registration with production numbers
☐ Verify OTP received in < 5 seconds
☐ Verify otp_delivery_logs table populated
☐ Check application logs for errors

Monitoring:
☐ Set up alerts for:
   - OTP delivery success_rate < 95%
   - OTP delivery latency > 5 seconds
   - Africa's Talking API errors

Rollback Plan:
☐ If issues in production:
   1. Set OTP_DELIVERY_ENABLED=false
   2. Restart application
   3. Users fall back to console OTP (development mode)
   4. Investigate issue with Africa's Talking logs
   5. Re-enable when fixed
```

#### Step 6.2: Configuration Template for Production
**File:** `.env.production` (example)

```env
# Database (production)
DATABASE_URL=postgresql+psycopg://prod_user:secure_password@prod.db.host:5432/remyafya_prod

# JWT & Security (production)
JWT_SECRET_KEY=production-secret-key-min-32-chars
SECRET_KEY=production-flask-secret-key

# Redis (production)
REDIS_URL=redis://:password@prod.redis.host:6379

# Flask
FLASK_APP=wsgi:app
FLASK_ENV=production
FLASK_DEBUG=False

# CORS
CORS_ORIGINS=https://app.remyafya.com,https://www.remyafya.com

# ━━━━━━━━━━━━━━━━ AFRICA'S TALKING - PRODUCTION ━━━━━━━━━━━━━━━━
AFRICAS_TALKING_API_KEY=<your-production-api-key>
AFRICAS_TALKING_USERNAME=<your-at-username>
AFRICAS_TALKING_SHORTCODE=<your-production-shortcode>
AFRICAS_TALKING_SENDER_ID=RemyAfya

# Feature Flags (production)
OTP_DELIVERY_METHOD=sms
OTP_DELIVERY_ENABLED=true
OTP_SANDBOX_MODE=false  # ← IMPORTANT: false for production

# Logging (production)
LOG_LEVEL=INFO
```

---

## Testing Strategy

### Unit Test Template
**File to Create:** `/tests/test_africas_talking_service.py`

```python
import pytest
from africas_talking_service import AfricasTalkingOTPService, send_otp
from unittest.mock import Mock, patch, MagicMock


class TestAfricasTalkingOTPService:
    """Test Africa's Talking OTP delivery service"""
    
    @mock.patch.dict(os.environ, {
        'AFRICAS_TALKING_API_KEY': 'test-key',
        'AFRICAS_TALKING_USERNAME': 'TestUser',
        'OTP_DELIVERY_ENABLED': 'true',
        'OTP_SANDBOX_MODE': 'true'
    })
    @mock.patch('africastalking.SMS')
    def test_send_otp_sms_success(self, mock_sms_class):
        """Test successful SMS OTP delivery"""
        # Setup mock
        mock_sms = MagicMock()
        mock_sms.send.return_value = {
            'SMSMessageData': {'Message': 'Sent'}
        }
        
        # Execute
        service = AfricasTalkingOTPService()
        success, msg = service.send_otp_sms('+254712345678', '12345')
        
        # Assert
        assert success == True
        assert 'success' in msg.lower()
    
    @mock.patch.dict(os.environ, {
        'OTP_DELIVERY_ENABLED': 'false'
    })
    def test_send_otp_disabled(self):
        """Test OTP delivery when disabled (console fallback)"""
        service = AfricasTalkingOTPService()
        success, msg = service.send_otp_sms('+254712345678', '12345')
        
        assert success == True
        assert 'Development' in msg or 'disabled' in msg.lower()


class TestOTPIntegration:
    """Integration tests for OTP with registration"""
    
    def test_registration_sends_otp(self, client, app):
        """Test that registration endpoint sends OTP"""
        with app.app_context():
            response = client.post('/api/v1/auth/register', json={
                'phone_number': '0712345678',
                'first_name': 'John',
                'last_name': 'Doe',
                'pin': '1234',
                'role': 'mother',
                'dob': '1995-01-15',
                'due_date': '2026-08-15',
                'ward_id': 1
            })
            
            assert response.status_code == 201
            assert response.json['otp_delivery_status'] in ['sent', 'pending_retry']
```

---

## Files Summary

### New Files to Create:
1. `/africas_talking_service.py` - Main OTP service  
2. `/migrations/036_create_otp_delivery_logs.sql` - Database table
3. `/tests/test_africas_talking_service.py` - Unit tests
4. `.env.production` - Production environment template

### Files to Modify:
1. `/requirements.txt` - Add dependencies
2. `/.env.example` - Add Africa's Talking config
3. `/auth.py` - Integrate OTP sending into registration & resend
4. `/app.py` - Initialize service at startup
5. `/models.py` - Add OTPDeliveryLog model

---

## Error Handling & Logging

### Log Message Prefixes
```
[AT]        - General Africa's Talking log
[AT-SMS]    - SMS delivery specific
[AT-WA]     - WhatsApp delivery specific
[OTP]       - OTP generic messages
[DEV]       - Development/console mode
```

### Common Errors & Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| "APIError: Invalid API key" | Wrong/expired API key | Update .env with correct sandbox/production key |
| "Connection timeout" | Network issue | Check internet, verify AT service status |
| "Invalid phone format" | Phone not in +254 format | Normalize phone numbers before sending |
| "SMS sending failed" | AT account issue | Check Africa's Talking dashboard logs |
| "Number blacklisted" | Recipient opted out | Use different test number |

---

## Monitoring & Metrics

### Key Metrics to Track
- **Delivery Success Rate** - Should be > 98%
- **Delivery Latency** - Should be < 5 seconds
- **Unique Phones Sent** - Track growth
- **Failed Attempts** - Alert if > 5% failure

### Prometheus Metrics (Future Enhancement)
```python
from prometheus_client import Counter, Histogram

otp_delivery_total = Counter(
    'otp_delivery_total', 
    'Total OTP delivery attempts',
    ['method', 'status']
)

otp_delivery_duration_seconds = Histogram(
    'otp_delivery_duration_seconds',
    'OTP delivery latency',
    ['method']
)
```

---

## Rollback Plan

If production issues occur:

1. **Immediate:** Set `OTP_DELIVERY_ENABLED=false`
   - Users will see console OTP (development mode)
   - Registration still works
   - No data loss

2. **Investigate:** Check Africa's Talking logs
   - API key validity
   - Rate limits reached
   - Network issues

3. **Fix & Re-enable:** Once issue resolved
   - Update configuration
   - Restart application
   - Verify with test registration

4. **Long-term:** Implement fallback service
   - Primary: Africa's Talking
   - Fallback: Twilio (or other provider)
   - Automatic failover

---

## Timeline

| Phase | Day | Tasks | Owner |
|-------|-----|-------|-------|
| **Setup** | 1 | 1.1-1.3: Dependencies, config, service module | Dev |
| **Database** | 1 | 2.1-2.2: Migration, model | Dev |
| **Integration** | 2 | 3.1-3.2: Update auth endpoints | Dev |
| **Startup** | 2 | 4.1: Initialize service | Dev |
| **Testing** | 2-3 | 5.1-5.2: Sandbox validation | QA + Dev |
| **Production** | 3 | 6.1-6.2: Migration checklist | DevOps + Dev |

**Total Estimated Time: 3 days**

---

## Next Steps

1. **Today (Day 1):**
   - Create africas_talking_service.py
   - Update .env.example
   - Create migration 036
   - Update requirements.txt

2. **Tomorrow (Day 2):**
   - Update auth.py registration & resend endpoints
   - Initialize service in app.py
   - Begin sandbox testing

3. **Day 3:**
   - Complete sandbox testing
   - Prepare production credentials
   - Migration checklist

---

## Support & Resources

**Africa's Talking Documentation:**
- https://africastalking.com/sms
- https://africastalking.com/whatsapp
- Sandbox account: https://africastalking.com/app/settings/api

**Python SDK:**
- https://github.com/africastalking/africastalking-python
- pip: `pip install africastalking`

**Troubleshooting:**
- Check AT account balance (if in production)
- Verify phone number format: +254xxxxxxxxx
- Check API key in .env matches dashboard
- Review app logs with [AT] prefix

---

## Sign-Off

**Backend Implementation:** Ready for Phase 1 setup  
**Estimated Effort:** 3 days  
**Risk Level:** Low (graceful fallback built-in)  
**Dependencies:** Sandbox Africa's Talking account

---

**Document Version:** 1.0  
**Last Updated:** 2026-04-13  
**Status:** ✓ Ready for Implementation
