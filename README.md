# RemyCareConnect Backend

A comprehensive healthcare management system backend with hybrid authentication, role-based access control, and Docker deployment.

## 🚀 Quick Start (Development)

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- PostgreSQL client (optional)

### Development Setup
1. **Start Docker services (DB + Redis):**
   ```bash
   docker-compose up -d
   ```

2. **Start Flask development server:**
   ```bash
   python start_dev.py
   # OR
   python test_server.py
   ```

3. **Verify Installation:**
   - Health Check: http://localhost:5001/api/v1/health
   - API Base URL: http://localhost:5001/api/v1
   - Postman Collection: `postman/collection.json` (configured for port 5001)

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
1. **Start services:** `docker-compose up -d` (PostgreSQL + Redis)
2. **Start backend:** `python start_dev.py` (Flask on localhost:5001)
3. **Features:**
   - Code changes auto-reload
   - Debug mode enabled
   - Real-time logs in terminal
   - Postman collection ready for testing


**RemyCareConnect Backend** - Healthcare Management System
Built with Flask, PostgreSQL, Redis, and Docker
