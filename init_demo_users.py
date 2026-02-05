#!/usr/bin/env python3
"""
Initialize demo users for testing the RemyCareConnect application.
Run this after database setup to have ready-to-use test accounts.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models import db, User, Mother, CHW, Nurse, Verification
from auth_utils import hash_pin, generate_otp

def init_demo_users():
    app = create_app()
    
    with app.app_context():
        print("🚀 Initializing demo users for RemyCareConnect...")
        
        # Demo users data
        demo_users = [
            {
                "phone_number": "+254700000001",
                "name": "Jane Doe",
                "pin": "1234",
                "role": "mother",
                "extra_data": {
                    "date_of_birth": "1995-06-15",
                    "due_date": "2026-08-15",
                    "location": "Nairobi"
                }
            },
            {
                "phone_number": "+254700000002", 
                "name": "Mary Wanjiku",
                "pin": "1234",
                "role": "chw",
                "extra_data": {
                    "specialization": "Maternal Health",
                    "location": "Nairobi"
                }
            },
            {
                "phone_number": "+254700000003",
                "name": "Grace Akinyi", 
                "pin": "1234",
                "role": "nurse",
                "extra_data": {
                    "specialization": "Obstetrics", 
                    "location": "Nairobi"
                }
            },
            {
                "phone_number": "+254700000004",
                "name": "Sarah Muthoni",
                "pin": "1234", 
                "role": "mother",
                "extra_data": {
                    "date_of_birth": "1992-03-20",
                    "due_date": "2026-07-10", 
                    "location": "Kisumu"
                }
            }
        ]
        
        for user_data in demo_users:
            try:
                # Check if user already exists
                existing_user = User.query.filter_by(phone_number=user_data["phone_number"]).first()
                if existing_user:
                    print(f"⏭️  User {user_data['name']} already exists, skipping...")
                    continue
                    
                # Create base user
                user = User(
                    phone_number=user_data["phone_number"],
                    name=user_data["name"], 
                    pin_hash=hash_pin(user_data["pin"]),
                    role=user_data["role"],
                    is_verified=True,  # Skip verification for demo
                    is_active=True,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                
                db.session.add(user)
                db.session.flush()  # Get user ID
                
                # Create role-specific records
                if user_data["role"] == "mother":
                    mother = Mother(
                        user_id=user.id,
                        mother_name=user_data["name"],
                        dob=user_data["extra_data"]["date_of_birth"],
                        due_date=user_data["extra_data"]["due_date"],
                        location=user_data["extra_data"]["location"],
                        created_at=datetime.now(timezone.utc)
                    )
                    db.session.add(mother)
                    
                elif user_data["role"] == "chw":
                    chw = CHW(
                        user_id=user.id,
                        chw_name=user_data["name"],
                        license_number=f"CHW{user.id:04d}",
                        location=user_data["extra_data"]["location"],
                        created_at=datetime.now(timezone.utc)
                    )
                    db.session.add(chw)
                    
                elif user_data["role"] == "nurse":
                    nurse = Nurse(
                        user_id=user.id,
                        nurse_name=user_data["name"],
                        license_number=f"NUR{user.id:04d}",
                        location=user_data["extra_data"]["location"],
                        created_at=datetime.now(timezone.utc)
                    )
                    db.session.add(nurse)
                
                db.session.commit()
                print(f"✅ Created demo {user_data['role']}: {user_data['name']} ({user_data['phone_number']})")
                
            except Exception as e:
                db.session.rollback()
                print(f"❌ Failed to create {user_data['name']}: {str(e)}")
                
        print("\n🎉 Demo users initialization completed!")
        print("\n📱 Login credentials (phone | PIN):")
        print("   Mother 1: +254700000001 | 1234")
        print("   CHW:      +254700000002 | 1234") 
        print("   Nurse:    +254700000003 | 1234")
        print("   Mother 2: +254700000004 | 1234")
        print("\n💡 These users are pre-verified and ready to use!")

if __name__ == "__main__":
    init_demo_users()