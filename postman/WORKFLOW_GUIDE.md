# RemyCareConnect Postman Collection - Complete Workflow Guide

## 📥 **Setup**

1. **Import Collection**: Import `collection.json` into Postman
2. **Backend Running**: Ensure backend is running at `http://localhost:5001`
3. **Database Ready**: PostgreSQL and Redis containers running

---

## 🎯 **Complete Mother Registration Workflow**

### **Step 1: Register as Mother**
**Endpoint:** `Authentication → Register User`

**Request Body:**
```json
{
  "phone_number": "+254712345678",
  "name": "Grace Wanjiku",
  "pin": "1234",
  "role": "mother"
}
```

**What Happens:**
- ✅ User account created in `users` table
- ✅ OTP generated and saved to `verifications` table
- ✅ Auto-saves: `user_id`, `otp_code` to environment variables

**Console Output:**
```
Registration successful. OTP: 123456
```

---

### **Step 2: Check OTP in Database**
**Option A - Use saved OTP:**
- Check console output for OTP code
- Variable `{{otp_code}}` is already set

**Option B - Query database:**
```sql
SELECT code, status, expires_at 
FROM verifications 
WHERE phone_number = '+254712345678'
ORDER BY created_at DESC LIMIT 1;
```

---

### **Step 3: Verify OTP**
**Endpoint:** `Authentication → Verify OTP`

**Request Body:**
```json
{
  "phone_number": "+254712345678",
  "otp_code": "{{otp_code}}"
}
```

**What Happens:**
- ✅ User verified in `users` table (`is_verified = true`)
- ✅ Verification status updated to 'verified'

---

### **Step 4: Login**
**Endpoint:** `Authentication → Login`

**Request Body:**
```json
{
  "phone_number": "+254712345678",
  "pin": "1234"
}
```

**What Happens:**
- ✅ JWT tokens generated (access + refresh)
- ✅ Session created in Redis
- ✅ Auto-saves: `access_token`, `refresh_token`, `user_id`, `user_role`
- ✅ All subsequent requests authenticated automatically

**Console Output:**
```
✅ Login successful!
👤 User: Grace Wanjiku (Role: mother)
🆔 User ID: 1
🎫 Token expires: 2026-02-06T12:00:00.000Z

➡️  Next step: Complete your profile using the Complete MOTHER Profile endpoint
```

---

### **Step 5: Complete Mother Profile**
**Endpoint:** `Mothers → Complete Mother Profile`

**Request Body:**
```json
{
  "dob": "1995-06-15",
  "due_date": "2026-09-20",
  "location": "Nairobi"
}
```

**What Happens:**
- ✅ Mother profile created in `mothers` table
- ✅ Links to your user_id automatically
- ✅ Auto-saves: `mother_id` to environment

**Console Output:**
```
✅ Mother profile completed successfully!
🆔 Mother ID: 1

➡️  You can now:
   - View profile: GET /mothers/1
   - Update profile: PUT /mothers/1
   - Add Next of Kin
```

---

### **Step 6: View Your Mother Profile**
**Endpoint:** `Mothers → Get My Mother Profile`

Uses `{{mother_id}}` variable automatically - no manual ID entry needed!

**Response:**
```json
{
  "mother_id": 1,
  "user_id": 1,
  "name": "Grace Wanjiku",
  "dob": "1995-06-15",
  "due_date": "2026-09-20",
  "location": "Nairobi",
  "phone": "+254712345678"
}
```

---

### **Step 7: Add Next of Kin**
**Endpoint:** `Next of Kin → Add My Next of Kin`

**Request Body:**
```json
{
  "user_id": {{mother_id}},
  "mother_name": "Grace Wanjiku",
  "name": "Peter Mwangi",
  "phone": "+254745678901",
  "sex": "Male",
  "relationship": "Husband"
}
```

**What Happens:**
- ✅ Next of kin record created in `next_of_kin` table
- ✅ Auto-saves: `nok_id` to environment
- ✅ Uses {{mother_id}} automatically

---

### **Step 8: Update Mother Profile (Optional)**
**Endpoint:** `Mothers → Update My Mother Profile`

**Request Body (all fields optional):**
```json
{
  "full_name": "Grace Wanjiku Mwangi",
  "due_date": "2026-10-01",
  "location": "Kiambu"
}
```

Uses `{{mother_id}}` automatically!

---

## 👨‍⚕️ **Complete CHW Registration Workflow**

### **Step 1: Register as CHW**
**Endpoint:** `Authentication → Register User`

**Request Body:**
```json
{
  "phone_number": "+254723456789",
  "name": "James Kiprotich",
  "pin": "1234",
  "role": "chw"
}
```

---

### **Step 2-4: Same as Mother**
Follow the same Verify OTP → Login flow

---

### **Step 5: Complete CHW Profile**
**Endpoint:** `CHWs → Complete CHW Profile`

**Request Body:**
```json
{
  "license_number": "CHW2026001",
  "location": "Nairobi Central Health Center"
}
```

**What Happens:**
- ✅ CHW profile created in `chws` table
- ✅ Auto-saves: `chw_id` to environment

---

### **Step 6: View Your CHW Profile**
**Endpoint:** `CHWs → Get My CHW Profile`

Uses `{{chw_id}}` automatically!

---

### **Step 7: Assign Mother to Your Care**
**Endpoint:** `CHWs → Assign Mother to Me`

**Request Body:**
```json
{
  "mother_id": {{mother_id}}
}
```

**What Happens:**
- ✅ Assignment created in `mother_chw_assignments` table
- ✅ Max 2 mothers per CHW enforced
- ✅ Uses {{chw_id}} and {{mother_id}} automatically

---

### **Step 8: View Your Assigned Mothers**
**Endpoint:** `CHWs → Get My Assigned Mothers`

Uses `{{chw_id}}` automatically!

---

## 👩‍⚕️ **Complete Nurse Registration Workflow**

### **Step 1: Register as Nurse**
**Endpoint:** `Authentication → Register User`

**Request Body:**
```json
{
  "phone_number": "+254734567890",
  "name": "Mary Akinyi",
  "pin": "1234",
  "role": "nurse"
}
```

---

### **Step 2-4: Same as Mother**
Follow Verify OTP → Login flow

---

### **Step 5: Complete Nurse Profile**
**Endpoint:** `Nurses → Complete Nurse Profile`

**Request Body:**
```json
{
  "license_number": "RN2026001",
  "location": "Kenyatta National Hospital"
}
```

**What Happens:**
- ✅ Nurse profile created in `nurses` table
- ✅ Auto-saves: `nurse_id` to environment

---

### **Step 6: View Your Nurse Profile**
**Endpoint:** `Nurses → Get My Nurse Profile`

Uses `{{nurse_id}}` automatically!

---

## 🔄 **Environment Variables Explained**

| Variable | Set By | Used For |
|----------|--------|----------|
| `base_url` | Manual | API base URL |
| `access_token` | Login | Authorization (auto) |
| `refresh_token` | Login | Token refresh |
| `token_expiry` | Login | Auto-refresh logic |
| `user_id` | Register/Login | Current user ID |
| `user_role` | Login | User role (mother/chw/nurse) |
| `mother_id` | Complete Mother Profile | Mother operations |
| `chw_id` | Complete CHW Profile | CHW operations |
| `nurse_id` | Complete Nurse Profile | Nurse operations |
| `otp_code` | Register/Resend OTP | OTP verification |
| `nok_id` | Add Next of Kin | NOK updates/deletes |

---

## 🔐 **Token Management**

### **Auto-Refresh**
- Collection automatically refreshes tokens before expiry
- Happens in pre-request script
- No manual intervention needed

### **Manual Refresh**
**Endpoint:** `Authentication → Refresh Token`

Uses `{{refresh_token}}` automatically

### **Re-login if Needed**
If tokens expire, just run Login endpoint again

---

## 🗂️ **Database Schema Quick Reference**

### **users table**
```
- id (PK, auto)
- phone_number (unique)
- name
- pin_hash
- role (mother/chw/nurse)
- is_verified (boolean)
- is_active (boolean)
- created_at
- updated_at
```

### **mothers table**
```
- id (PK, auto)
- user_id (FK → users.id, unique)
- mother_name
- dob (date)
- due_date (date)
- location
- created_at
```

### **chws table**
```
- id (PK, auto)
- user_id (FK → users.id, unique)
- chw_name
- license_number
- location
- created_at
```

### **nurses table**
```
- id (PK, auto)
- user_id (FK → users.id, unique)
- nurse_name
- license_number
- location
- created_at
```

### **next_of_kin table**
```
- id (PK, auto)
- user_id (FK → mothers.id)
- mother_name
- name
- phone
- sex
- relationship
- created_at
```

### **verifications table**
```
- id (PK, auto)
- user_id (FK → users.id)
- phone_number
- code (6-digit OTP)
- status (pending/verified/expired)
- created_at
- expires_at (10 minutes)
```

### **mother_chw_assignments table**
```
- id (PK, auto)
- mother_id (FK → mothers.id)
- mother_name
- chw_id (FK → chws.id)
- chw_name
- assigned_at
- status (active/inactive)
```

**Constraint:** Max 2 active mothers per CHW

---

## 💡 **Tips & Best Practices**

### **1. Dynamic IDs - No More Hardcoding!**
✅ **GOOD:** `{{base_url}}/api/v1/mothers/{{mother_id}}`
❌ **BAD:** `{{base_url}}/api/v1/mothers/1`

All profile endpoints now use dynamic variables!

### **2. Check Console Logs**
After each request, check Postman console for:
- Success messages
- Auto-saved variable values
- Next step suggestions

### **3. Testing Multiple Users**
To test different users:
1. Use different phone numbers
2. Run full workflow for each
3. Variables update for current logged-in user

### **4. Get OTP from Database**
```sql
-- Latest OTP for phone
SELECT code, status, expires_at 
FROM verifications 
WHERE phone_number = '+254...'
ORDER BY created_at DESC LIMIT 1;

-- All pending OTPs
SELECT u.name, v.phone_number, v.code, v.expires_at
FROM verifications v
JOIN users u ON v.user_id = u.id
WHERE v.status = 'pending'
ORDER BY v.created_at DESC;
```

### **5. Complete Profiles in Order**
1. Register → Verify OTP → Login (for all roles)
2. Complete Profile (mother/chw/nurse)
3. Then use role-specific features

### **6. Update vs Complete Profile**
- **Complete Profile:** First time only, creates record
- **Update Profile:** Modify existing record, partial updates allowed

---

## 🐛 **Troubleshooting**

### **Issue: "Mother profile already exists"**
**Cause:** You already completed the profile
**Solution:** Use "Update My Mother Profile" instead

### **Issue: "Invalid OTP code"**
**Causes:**
1. OTP expired (10 minutes)
2. Wrong code
3. Already verified

**Solutions:**
1. Use "Resend OTP" endpoint
2. Check database for latest OTP
3. Check if already verified in users table

### **Issue: "CHW already has 2 active mothers"**
**Cause:** CHW assignment limit reached
**Solution:** Assign to different CHW or deactivate an assignment

### **Issue: Variables not set**
**Cause:** Test scripts not running
**Solution:**
1. Check Postman console for errors
2. Re-run the request
3. Check response matches expected format

### **Issue: 401 Unauthorized**
**Causes:**
1. Not logged in
2. Token expired
3. Wrong role for endpoint

**Solutions:**
1. Run Login endpoint
2. Check `{{access_token}}` is set
3. Use Refresh Token or re-login

---

## 📊 **Useful Database Queries**

### **View Complete Mother Profile**
```sql
SELECT 
    u.phone_number,
    u.name,
    u.role,
    u.is_verified,
    m.dob,
    m.due_date,
    m.location,
    nok.name as nok_name,
    nok.phone as nok_phone,
    nok.relationship
FROM users u
JOIN mothers m ON u.id = m.user_id
LEFT JOIN next_of_kin nok ON m.id = nok.user_id
WHERE u.phone_number = '+254712345678';
```

### **View CHW with Assigned Mothers**
```sql
SELECT 
    c.chw_name,
    c.license_number,
    COUNT(ma.mother_id) as total_assigned,
    STRING_AGG(ma.mother_name, ', ') as mothers
FROM chws c
LEFT JOIN mother_chw_assignments ma ON c.id = ma.chw_id AND ma.status = 'active'
WHERE c.id = 1
GROUP BY c.id, c.chw_name, c.license_number;
```

### **List All Users by Role**
```sql
SELECT role, COUNT(*) as count
FROM users
WHERE is_verified = true
GROUP BY role;
```

---

## ✅ **Collection Features**

### **✨ What's Optimized:**

1. **🎯 Dynamic ID Tracking**
   - Auto-extracts and saves IDs from responses
   - No more hardcoded `/mothers/1` - uses `{{mother_id}}`
   - Works for mother_id, chw_id, nurse_id, nok_id

2. **🤖 Smart Variables**
   - Auto-saves tokens, user_id, role, profile IDs
   - Auto-refreshes expired tokens
   - Clears tokens on logout

3. **📝 Complete Request Bodies**
   - All endpoints have proper example bodies
   - Uses realistic Kenya data (+254 phones, Nairobi locations)
   - Comments explain required vs optional fields

4. **💬 Console Feedback**
   - Success messages with extracted IDs
   - Next step suggestions
   - Clear error messages

5. **📖 Detailed Descriptions**
   - Every endpoint documented
   - Field requirements explained
   - Database schema references

6. **🔗 Workflow-Oriented**
   - Organized by user flow
   - Clear step-by-step process
   - Role-specific sections

---

## 🎓 **Learning Path**

### **For Testing:**
1. Start with Mother workflow (simplest)
2. Then CHW workflow (includes assignments)
3. Finally Nurse workflow (for escalations)

### **For Development:**
1. Understand token flow (register → verify → login)
2. Learn profile completion pattern
3. Study relationship between tables
4. Practice with dynamic variables

---

**Last Updated:** February 5, 2026
**Collection Version:** v5.0 - Optimized & Dynamic
**Backend Version:** Compatible with RemyCareConnect API v1

---

## 🚀 **Quick Start Checklist**

- [ ] Backend running at http://localhost:5001
- [ ] Collection imported into Postman
- [ ] Health check passed
- [ ] Register mother → Verify → Login → Complete profile
- [ ] Check console logs for auto-saved IDs
- [ ] Update profile using {{mother_id}}
- [ ] Add next of kin
- [ ] 🎉 Success!

