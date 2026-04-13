# Africa's Talking OTP Implementation - Quick Reference Checklist

**Status:** Sandbox Setup Phase  
**Start Date:** 2026-04-13  
**Estimated Duration:** 3 days

---

## Phase 1: Dependencies & Configuration

### Day 1 - Morning

- [ ] **1.1 Install Dependencies**
  ```bash
  pip install requests africastalking
  pip install -r requirements.txt  # Update requirements.txt first
  ```
  Files: `requirements.txt`

- [ ] **1.2 Add Environment Variables**
  ```
  .env - Add new variables (copy from main plan)
  .env.example - Update with Africa's Talking config
  ```
  
  **Key Variables:**
  - AFRICAS_TALKING_API_KEY=your-sandbox-key
  - AFRICAS_TALKING_USERNAME=RemyAfya
  - AFRICAS_TALKING_SHORTCODE=20880
  - OTP_DELIVERY_ENABLED=true
  - OTP_SANDBOX_MODE=true

- [ ] **1.3 Create OTP Service Module**
  ```
  File: /africas_talking_service.py
  Contains: AfricasTalkingOTPService class
  Size: ~300 lines
  Status: Copy from implementation plan
  ```

**Checkpoint:** Service module created, environment configured

---

## Phase 2: Database Setup

### Day 1 - Afternoon

- [ ] **2.1 Create Migration File**
  ```
  File: /migrations/036_create_otp_delivery_logs.sql
  Table: otp_delivery_logs
  Columns: id, phone_number, method, success, error_message, created_at
  ```

- [ ] **2.2 Run Migration**
  ```bash
  # Option 1: Using Flask-Migrate
  python -m flask db upgrade
  
  # Option 2: Direct SQL
  psql -U postgres -d remyafya -f migrations/036_create_otp_delivery_logs.sql
  ```

- [ ] **2.3 Verify Table Created**
  ```bash
  psql -U postgres -d remyafya -c "\dt otp_delivery_logs;"
  ```

- [ ] **2.4 (Optional) Add Model**
  ```
  File: /models.py
  Add: OTPDeliveryLog class
  Methods: Standard SQLAlchemy model
  ```

**Checkpoint:** Database table ready, can accept logs

---

## Phase 3: Update Auth Endpoints

### Day 2 - Morning

- [ ] **3.1 Modify Registration Endpoint**
  ```
  File: /auth.py
  Function: register()
  Changes:
  - Import africas_talking_service
  - After OTP created: call send_otp()
  - Log delivery status
  - Return otp_delivery_status to client
  ```

- [ ] **3.2 Modify Resend OTP Endpoint**
  ```
  File: /auth.py
  Function: resend_otp()
  Changes:
  - After OTP created: call send_otp()
  - Log delivery status
  - Return otp_delivery_status to client
  ```

- [ ] **3.3 Test Modifications**
  ```bash
  # Start server
  python -m flask run
  
  # Test endpoint
  curl -X POST http://localhost:5000/api/v1/auth/register \
    -H "Content-Type: application/json" \
    -d '{
      "phone_number": "0712345678",
      "first_name": "John",
      "last_name": "Doe",
      "pin": "1234",
      "role": "mother",
      "dob": "1995-01-15",
      "due_date": "2026-08-15",
      "ward_id": 1
    }'
  ```

**Checkpoint:** Endpoints send OTP, logging works

---

## Phase 4: App Initialization

### Day 2 - Afternoon

- [ ] **4.1 Update app.py**
  ```
  File: /app.py
  Location: In create_app() function
  Add: initialize get_otp_service()
  Result: "✓ Africa's Talking initialized" in logs
  ```

- [ ] **4.2 Test Startup**
  ```bash
  python -m flask run
  # Check for: "[AT] Initialized in SANDBOX mode"
  ```

**Checkpoint:** Service initializes on startup

---

## Phase 5: Sandbox Testing

### Day 2-3

#### 5.1 Normal Flow Test
```
☐ Register new user with valid data
  ├─ Phone: 0712345678
  ├─ Role: mother (or chw/nurse)
  ├─ Response: 201 with otp_delivery_status='sent'
  └─ Check: OTP received (sandbox may print to console)

☐ Verify OTP received
  ├─ Check Africa's Talking dashboard
  ├─ Or check application logs
  └─ Or check database: SELECT * FROM otp_delivery_logs LIMIT 1

☐ Submit verification
  ├─ POST /api/v1/auth/verify-otp
  ├─ Response: 200, user verified
  └─ Check: users.is_verified = true
```

#### 5.2 Error Cases
```
☐ Invalid phone format
  ├─ Send: "123456" (invalid)
  └─ Expected: 400 error

☐ Duplicate registration
  ├─ Register phone X successfully
  ├─ Register phone X again
  └─ Expected: 409 conflict

☐ Wrong OTP code
  ├─ Register user
  ├─ Submit wrong verification code
  └─ Expected: 400 error

☐ Expired OTP
  ├─ Register user
  ├─ Wait 10+ minutes
  ├─ Submit original code
  └─ Expected: 400 "expired" error

☐ Resend OTP
  ├─ Register user
  ├─ POST /resend-otp
  └─ Expected: 200, new OTP sent
```

#### 5.3 Database Checks
```sql
-- Check delivery logs
SELECT * FROM otp_delivery_logs ORDER BY created_at DESC LIMIT 10;

-- Success rate
SELECT 
    method,
    COUNT(*) as total,
    SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful,
    ROUND(100.0 * SUM(CASE WHEN success THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate
FROM otp_delivery_logs
GROUP BY method;

-- Recent verifications
SELECT u.phone_number, v.status, v.created_at 
FROM verifications v 
JOIN users u ON u.id = v.user_id 
ORDER BY v.created_at DESC LIMIT 5;
```

**Checkpoint:** All test cases pass, logging works

---

## Phase 6: Production Preparation

### Day 3

#### 6.1 Pre-Production Checklist
```
☐ Load test: 10+ concurrent registrations
☐ Verify success_rate > 98%
☐ Check delivery latency < 5 seconds
☐ Review error logs for issues
☐ Get production Africa's Talking credentials
☐ Test a few registrations with real test numbers
```

#### 6.2 Prepare Production Environment
```
☐ Create .env.production file
☐ Update values:
   - AFRICAS_TALKING_API_KEY=<production_key>
   - OTP_SANDBOX_MODE=false
   - Other credentials from AT dashboard

☐ Create backup of current .env (in case rollback needed)
☐ Document all production credentials securely
```

#### 6.3 Deployment Plan
```
When ready to deploy:
1. Update production .env
2. Restart backend service
3. Verify startup: "Africa's Talking initialized (PRODUCTION mode)"
4. Test registration with real number
5. Verify SMS received < 5 seconds
6. Monitor error logs for first hour
7. If issues: Set OTP_DELIVERY_ENABLED=false and restart
```

**Checkpoint:** Production ready, rollback plan clear

---

## File Changes Summary

### New Files (Create)
```
✓ /africas_talking_service.py          (~300 lines)
✓ /migrations/036_create_otp_delivery_logs.sql
✓ /tests/test_africas_talking_service.py (optional)
✓ .env.production (template)
```

### Modified Files (Add to)
```
✓ /requirements.txt                    (add: africastalking>=1.2.4)
✓ /.env.example                        (add: AT config vars)
✓ /auth.py                             (send_otp in register/resend)
✓ /app.py                              (initialize service)
✓ /models.py                           (add OTPDeliveryLog model - optional)
```

### No Changes
```
- Existing endpoints remain backward compatible
- OTP verification flow unchanged
- Database schema only adds new table (no migrations)
```

---

## Command Reference

### Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Run migration
python -m flask db upgrade

# Start server
python -m flask run
```

### Testing
```bash
# Test registration
curl -X POST http://localhost:5000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"0712345678","first_name":"John","last_name":"Doe","pin":"1234","role":"mother","dob":"1995-01-15","due_date":"2026-08-15","ward_id":1}'

# Check database
psql -U postgres -d remyafya -c "SELECT * FROM otp_delivery_logs LIMIT 5;"
```

### Troubleshooting
```bash
# Check application logs
tail -f app.log | grep "[AT]"

# Verify Africa's Talking initialized
python -c "from africas_talking_service import get_otp_service; s = get_otp_service(); print('Service ready')"

# Check if credentials are loaded
python -c "import os; print(f'API Key: {os.getenv(\"AFRICAS_TALKING_API_KEY\")[:10]}...')"
```

---

## Environment Variable Checklist

### Sandbox Environment (.env)
```
AFRICAS_TALKING_API_KEY=<your-sandbox-key>
AFRICAS_TALKING_USERNAME=RemyAfya
AFRICAS_TALKING_SHORTCODE=20880
AFRICAS_TALKING_SENDER_ID=RemyAfya

OTP_DELIVERY_METHOD=sms
OTP_DELIVERY_ENABLED=true
OTP_SANDBOX_MODE=true

LOG_LEVEL=INFO
```

### Production Environment (.env.production)
```
AFRICAS_TALKING_API_KEY=<your-production-key>
AFRICAS_TALKING_USERNAME=RemyAfya
AFRICAS_TALKING_SHORTCODE=<your-production-shortcode>
AFRICAS_TALKING_SENDER_ID=RemyAfya

OTP_DELIVERY_METHOD=sms
OTP_DELIVERY_ENABLED=true
OTP_SANDBOX_MODE=false  ← IMPORTANT: false for production

LOG_LEVEL=INFO
```

---

## Fallback & Rollback

### If OTP Sending Fails in Production:
```bash
# 1. Disable OTP delivery immediately
Edit .env: OTP_DELIVERY_ENABLED=false

# 2. Restart backend
systemctl restart remyafya-backend

# 3. Users get console OTP (development mode)
# Registration still works, just logs OTP to console

# 4. Investigate issue
Check Africa's Talking dashboard logs
Check API key validity
Check account balance (if production)

# 5. Re-enable when fixed
Edit .env: OTP_DELIVERY_ENABLED=true
systemctl restart remyafya-backend
```

---

## Success Criteria

✓ **Setup Phase:**
- [ ] Dependencies installed
- [ ] Africa's Talking service module created
- [ ] Environment variables configured
- [ ] Migration created and applied

✓ **Integration Phase:**
- [ ] Auth endpoints call send_otp()
- [ ] OTP delivery logged to database
- [ ] Response includes delivery status

✓ **Testing Phase:**
- [ ] Sandbox test registrations send OTP
- [ ] OTP verification works correctly
- [ ] Error cases handled properly
- [ ] Logs show [AT] messages

✓ **Production Ready:**
- [ ] Success rate > 98% in sandbox
- [ ] Delivery latency < 5 seconds
- [ ] Production credentials secured
- [ ] Rollback plan documented
- [ ] Support team trained

---

## Timeline

| Phase | Duration | Date | Status |
|-------|----------|------|--------|
| Dependencies & Config | 1 day | Day 1 | ⬜ TODO |
| Database Setup | 1 day | Day 1 | ⬜ TODO |
| Auth Integration | 1 day | Day 2 | ⬜ TODO |
| Testing & Validation | 1 day | Day 2-3 | ⬜ TODO |
| Production Prep | 0.5 day | Day 3 | ⬜ TODO |

**Total: 3 days**

---

## Support Resources

**Africa's Talking:**
- Dashboard: https://africastalking.com/app/dashboard
- SMS Docs: https://africastalking.com/sms
- API Status: https://status.africastalking.com/

**Python Library:**
- GitHub: https://github.com/africastalking/africastalking-python
- Installation: `pip install africastalking`
- Example: See implementation plan

**This Project:**
- Main Plan: AFRICAS_TALKING_OTP_IMPLEMENTATION_PLAN.md
- Code: See modules in backend/
- Tests: /tests/test_africas_talking_service.py

---

**Version:** 1.0  
**Last Updated:** 2026-04-13  
**Ready for:** Phase 1 Begin  
**Owner:** Backend Team
