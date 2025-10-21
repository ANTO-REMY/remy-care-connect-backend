#!/usr/bin/env python3
"""
Setup script for hybrid authentication system
Run this after implementing the auth system to create necessary database tables
"""

from app import create_app, db
from models import User, UserSession, Verification, Mother, CHW, Nurse
from flask_migrate import upgrade, migrate, init
import os

def setup_database():
    """Initialize database and create tables"""
    app = create_app()
    
    with app.app_context():
        print("🔧 Setting up hybrid authentication database...")
        
        # Create all tables
        db.create_all()
        print("✅ Database tables created successfully")
        
        # Check if migration directory exists
        if not os.path.exists('migrations'):
            print("🔄 Initializing Flask-Migrate...")
            init()
            print("✅ Flask-Migrate initialized")
        
        # Create migration for new auth fields
        print("🔄 Creating migration for hybrid auth...")
        migrate(message="Add hybrid authentication fields")
        print("✅ Migration created")
        
        # Apply migration
        print("🔄 Applying database migration...")
        upgrade()
        print("✅ Migration applied successfully")
        
        print("\n🎉 Hybrid authentication setup complete!")
        print("\n📋 Next steps:")
        print("1. Install dependencies: pip install -r requirements.txt")
        print("2. Start Redis server: redis-server")
        print("3. Run the Flask app: python wsgi.py")
        print("4. Import the new Postman collection: collection_hybrid_auth.json")
        print("5. Test the authentication endpoints")

if __name__ == '__main__':
    setup_database()
