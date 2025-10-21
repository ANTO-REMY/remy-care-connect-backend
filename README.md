# RemyCareConnect Backend

A comprehensive healthcare management system backend with hybrid authentication, role-based access control, and Docker deployment.

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Git

### 1. Clone and Setup
```bash
git clone <your-repo-url>
cd remy-care-connect/backend
```

### 2. Start the Application

**Windows:**
```cmd
start.bat
```

**Linux/Mac:**
```bash
chmod +x start.sh
./start.sh
```

**Development Mode:**
```bash
chmod +x start-dev.sh
./start-dev.sh
```

### 3. Verify Installation
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

## 📚 API Documentation

### Authentication Endpoints
```
POST /api/v1/auth/register     - Register new user
POST /api/v1/auth/verify-otp   - Verify phone number
POST /api/v1/auth/login        - Login with credentials
POST /api/v1/auth/refresh      - Refresh access token
GET  /api/v1/auth/profile      - Get user profile
POST /api/v1/auth/logout       - Logout current session
POST /api/v1/auth/logout-all   - Logout all sessions
```

### Profile Completion Endpoints
```
POST /api/v1/mothers/complete-profile  - Complete mother profile
POST /api/v1/chws/complete-profile     - Complete CHW profile
POST /api/v1/nurses/complete-profile   - Complete nurse profile
```

### Resource Endpoints
```
GET    /api/v1/mothers         - List mothers (CHW/Nurse only)
GET    /api/v1/chws           - List CHWs (CHW/Nurse only)
GET    /api/v1/nurses         - List nurses (Nurse only)
```

For complete API documentation, see [AUTH_README.md](AUTH_README.md)

## 🔧 Configuration

### Environment Variables
```bash
# Database
DATABASE_URL=postgresql+psycopg://postgres:postgres@db:5432/remyafya
POSTGRES_DB=remyafya
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# Authentication
JWT_SECRET_KEY=your-jwt-secret-key
SECRET_KEY=your-flask-secret-key

# Redis
REDIS_URL=redis://redis:6379

# Flask
FLASK_ENV=development
FLASK_DEBUG=True
```

## 🧪 Testing

### Using Postman
1. Import collection: `postman/collection_hybrid_auth.json`
2. The collection handles token management automatically
3. Test the complete authentication flow

### Manual Testing
```bash
# Health check
curl http://localhost:5000/api/v1/health

# Register user
curl -X POST http://localhost:5000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+1234567890", "name": "Test User", "pin": "1234", "role": "mother"}'
```

## 🐳 Docker Commands

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f backend

# Stop services
docker-compose down

# Rebuild and start
docker-compose up --build -d

# Development mode
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

## 📁 Project Structure

```
backend/
├── app.py                 # Flask application factory
├── wsgi.py               # WSGI entry point
├── models.py             # Database models
├── auth.py               # Authentication routes
├── auth_utils.py         # Authentication utilities
├── database.py           # Database utilities
├── init_db.py            # Database initialization
├── requirements.txt      # Python dependencies
├── Dockerfile           # Container definition
├── docker-compose.yml   # Service orchestration
├── .env                 # Environment variables
├── routes/              # API route modules
│   ├── routes_health.py
│   ├── routes_mothers.py
│   ├── routes_chws.py
│   ├── routes_nurses.py
│   └── ...
├── postman/             # API testing collections
├── migrations/          # Database migrations
└── start.sh            # Startup scripts
```

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

## 🛠️ Troubleshooting

### Common Issues

**Database Connection Error:**
```bash
# Check if PostgreSQL is running
docker-compose ps db

# View database logs
docker-compose logs db
```

**Redis Connection Error:**
```bash
# Check if Redis is running
docker-compose ps redis

# Test Redis connection
docker-compose exec redis redis-cli ping
```

**Port Already in Use:**
```bash
# Find process using port 5000
netstat -tulpn | grep :5000

# Kill process (Linux/Mac)
sudo kill -9 <PID>
```

### Reset Database
```bash
# Stop services
docker-compose down

# Remove volumes
docker-compose down -v

# Restart with fresh database
./start.sh
```

## 📞 Support

For issues or questions:
1. Check the logs: `docker-compose logs -f backend`
2. Verify environment configuration
3. Test with Postman collection
4. Review [AUTH_README.md](AUTH_README.md) for authentication details

## 🔄 Updates

To update the application:
```bash
git pull origin main
docker-compose down
docker-compose up --build -d
```

---

**RemyCareConnect Backend** - Healthcare Management System
Built with Flask, PostgreSQL, Redis, and Docker
