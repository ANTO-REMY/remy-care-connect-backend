# RemyCareConnect Backend

A comprehensive healthcare management system backend with hybrid authentication, role-based access control, and Docker deployment.




### Verify Installation
- Health Check: http://localhost:5000/api/v1/health
- API Base URL: http://localhost:5000/api/v1

## 🏗️ Architecture

### Services
- **Backend**: Flask API with hybrid authentication
- **Database**: PostgreSQL 15
- **Cache/Sessions**: Redis 7
- **Reverse Proxy**: Ready for Nginx (production)

### Key Features
- ✅ **Hybrid Authentication**: JWT + Session-based
- ✅ **Role-based Access Control**: Mother, CHW, Nurse roles
- ✅ **OTP Verification**: Phone number verification
- ✅ **Multi-device Support**: Session management
- ✅ **Docker Deployment**: Production-ready containers
- ✅ **CORS Support**: Frontend integration ready
- ✅ **Database Migrations**: Flask-Migrate integration


## 🔒 Security Features

- **PIN Hashing**: SHA256 with secure verification
- **JWT Tokens**: Signed with secret key, 24-hour expiry
- **Session Management**: Redis-based with device tracking
- **Role-based Access**: Granular permissions per endpoint
- **CORS Protection**: Configured for frontend origins
- **Input Validation**: Comprehensive request validation

## 🚀 Deployment

### Production Deployment
1. Update environment variables in `.env`
2. Set strong secret keys
3. Configure database credentials
4. Run: `./start.sh`

### Development Deployment
1. Run: `./start-dev.sh`
2. Code changes auto-reload
3. Debug mode enabled


**RemyCareConnect Backend** - Healthcare Management System
Built with Flask, PostgreSQL, Redis, and Docker
