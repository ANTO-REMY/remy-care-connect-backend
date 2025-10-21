#!/usr/bin/env python3
"""
Database initialization script for RemyCareConnect
Creates all tables and sets up the database schema
"""

from app import create_app, db
from models import (
    User, UserSession, Verification, Mother, CHW, Nurse,
    AppointmentSchedule, MedicalRecordType, EducationalMaterial,
    DietaryRecommendation, NextOfKin
)
import os

def init_database():
    """Initialize database and create all tables"""
    app = create_app()
    
    with app.app_context():
        print("🔧 Initializing RemyCareConnect database...")
        
        # Drop all tables if they exist (for fresh start)
        if os.getenv('RESET_DB', 'false').lower() == 'true':
            print("⚠️  Dropping existing tables...")
            db.drop_all()
        
        # Create all tables
        print("📋 Creating database tables...")
        db.create_all()
        
        # Verify tables were created
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        
        expected_tables = [
            'users', 'user_sessions', 'verifications', 'mothers', 
            'chws', 'nurses', 'appointment_schedule', 'medical_record_type',
            'educational_material', 'dietary_recommendation', 'next_of_kin'
        ]
        
        created_tables = [table for table in expected_tables if table in tables]
        missing_tables = [table for table in expected_tables if table not in tables]
        
        print(f"✅ Created {len(created_tables)} tables: {', '.join(created_tables)}")
        
        if missing_tables:
            print(f"⚠️  Missing tables: {', '.join(missing_tables)}")
        
        print("\n🎉 Database initialization complete!")
        print("\n📋 Next steps:")
        print("1. Start the services: docker-compose up -d")
        print("2. Test the health endpoint: curl http://localhost:5000/api/v1/health")
        print("3. Import Postman collection: postman/collection_hybrid_auth.json")
        print("4. Test authentication flow")

if __name__ == '__main__':
    init_database()
