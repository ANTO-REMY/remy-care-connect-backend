# Hybrid Authentication System - RemyCareConnect

## Overview
This system implements hybrid authentication using both JWT tokens and server-side sessions, providing flexibility for different client types while maintaining security.

## Features
- ✅ **Hybrid Authentication**: JWT + Session-based
- ✅ **24-hour Token Expiry**: Configurable token lifetime
- ✅ **Multi-device Support**: Users can login from multiple devices
- ✅ **OTP Verification**: Phone number verification during registration
- ✅ **Role-based Access**: Mother, CHW, Nurse roles with different permissions
- ✅ **Automatic Token Refresh**: Postman collection handles token refresh automatically
- ✅ **Self-registration**: All user types can register themselves

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Setup Environment
```bash
cp .env.example .env
# Edit .env with your configuration
```

### 3. Setup Database
```bash
python setup_auth.py
```

### 4. Start Services
```bash
# Start Redis (required for sessions)
redis-server

# Start Flask app
python wsgi.py
```

### 5. Import Postman Collection
Import `postman/collection_hybrid_auth.json` into Postman for automatic token handling.

## Authentication Flow

### Registration Flow
1. **Register**: `POST /api/v1/auth/register`
   - Provide: phone_number, name, pin, role
   - Returns: user_id, otp_code (for testing)

2. **Verify OTP**: `POST /api/v1/auth/verify-otp`
   - Provide: phone_number, otp_code
   - Activates the account

3. **Complete Profile**: Role-specific endpoints
   - Mothers: `POST /api/v1/mothers/complete-profile`
   - CHWs: `POST /api/v1/chws/complete-profile`
   - Nurses: `POST /api/v1/nurses/complete-profile`

### Login Flow
1. **Login**: `POST /api/v1/auth/login`
   - Provide: phone_number, pin
   - Returns: access_token, refresh_token, user info
   - Sets server-side session automatically

2. **Access Protected Routes**: Include `Authorization: Bearer <access_token>` header

3. **Token Refresh**: `POST /api/v1/auth/refresh`
   - Automatic in Postman collection
   - Use refresh_token to get new access_token

## API Endpoints

### Authentication
- `POST /auth/register` - Register new user
- `POST /auth/verify-otp` - Verify phone number
- `POST /auth/login` - Login with credentials
- `POST /auth/refresh` - Refresh access token
- `GET /auth/profile` - Get current user profile
- `POST /auth/logout` - Logout current session
- `POST /auth/logout-all` - Logout all other sessions
- `POST /auth/resend-otp` - Resend OTP code

### Protected Routes
All routes except auth endpoints require authentication:
- `Authorization: Bearer <access_token>` header, OR
- Valid server-side session

### Role-based Access
- **Mothers**: Can access their own profile and related data
- **CHWs**: Can access mother profiles and manage assignments
- **Nurses**: Can access all profiles and manage medical records

## Database Schema

### New Tables
- `user_sessions`: Stores active sessions for hybrid auth
- `users`: Extended with `is_verified`, `is_active` fields

### Updated Tables
- `users`: Added verification and status fields
- `verifications`: Used for OTP verification flow

## Security Features

### Token Security
- JWT tokens signed with secret key
- 24-hour access token expiry
- 30-day refresh token expiry
- Automatic token refresh in Postman

### Session Security
- Redis-based session storage
- Session tokens with expiry
- Device and IP tracking
- Multi-device support

### Password Security
- PIN hashing with SHA256
- No plain text storage
- Secure verification process

## Configuration

### Environment Variables
```bash
# Database
DATABASE_URL=postgresql://user:pass@host:port/db

# JWT
JWT_SECRET_KEY=your-jwt-secret
SECRET_KEY=your-flask-secret

# Redis
REDIS_URL=redis://localhost:6379
```

### Token Configuration
- Access Token: 24 hours (86400 seconds)
- Refresh Token: 30 days (2592000 seconds)
- OTP Expiry: 10 minutes

## Testing with Postman

### Automatic Features
- ✅ **Token Storage**: Login automatically stores tokens
- ✅ **Token Refresh**: Auto-refreshes before expiry
- ✅ **OTP Handling**: Stores OTP codes automatically
- ✅ **Environment Variables**: All tokens managed automatically

### Test Sequence
1. Register a new user
2. Verify OTP (auto-filled from registration)
3. Login (tokens stored automatically)
4. Access protected endpoints (auth header added automatically)
5. Test token refresh (happens automatically)

## Troubleshooting

### Common Issues
1. **Redis Connection**: Ensure Redis server is running
2. **Database Migration**: Run `python setup_auth.py`
3. **Token Expiry**: Check Postman environment variables
4. **OTP Issues**: Check verification table in database

### Debug Mode
Set `FLASK_DEBUG=True` in environment for detailed error messages.

## Future Enhancements
- WhatsApp/SMS integration for OTP delivery
- Password reset functionality
- Account lockout after failed attempts
- Audit logging for security events
- OAuth integration (Google, Facebook)

## Support
For issues or questions, check the database logs and Flask debug output.
