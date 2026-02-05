#!/usr/bin/env python3
"""
Fix users registered through Postman by ensuring they're verified and have proper phone format
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from app import create_app
from models import db, User
import re

def normalize_phone_number(phone):
    """Normalize phone number to +254xxx format"""
    # Remove all spaces and special characters except +
    cleaned = re.sub(r'[^0-9+]', '', phone)
    
    # Handle different formats
    if cleaned.startswith('07') and len(cleaned) == 10:
        # Convert 07xxxxxxxx to +254xxxxxxxx
        return '+254' + cleaned[1:]
    elif cleaned.startswith('+2547') and len(cleaned) == 13:
        # Convert +2547xxxxxxxx to +254xxxxxxxx
        return '+254' + cleaned[5:]
    elif cleaned.startswith('+254') and len(cleaned) == 13:
        # Already in correct format - don't modify
        return cleaned
    elif cleaned.startswith('254') and len(cleaned) == 12:
        # Convert 254xxxxxxxx to +254xxxxxxxx
        return '+' + cleaned
    
    # If none of the above, return as is (will fail validation)
    return phone

def fix_postman_users():
    """Fix users that were registered through Postman"""
    app = create_app()
    
    with app.app_context():
        try:
            print("🔧 Checking users registered through Postman...")
            
            users = User.query.all()
            fixed_count = 0
            
            for user in users:
                updated = False
                
                # Ensure user is verified
                if not user.is_verified:
                    print(f"📱 Verifying user: {user.phone_number} ({user.name})")
                    user.is_verified = True
                    updated = True
                
                # Ensure user is active
                if not user.is_active:
                    print(f"✅ Activating user: {user.phone_number} ({user.name})")
                    user.is_active = True
                    updated = True
                
                # Normalize phone number if needed
                normalized_phone = normalize_phone_number(user.phone_number)
                if normalized_phone != user.phone_number:
                    print(f"📞 Normalizing phone: {user.phone_number} → {normalized_phone}")
                    user.phone_number = normalized_phone
                    updated = True
                
                if updated:
                    fixed_count += 1
            
            if fixed_count > 0:
                db.session.commit()
                print(f"✅ Fixed {fixed_count} users")
            else:
                print("✅ All users are already properly configured")
                
            # Show all users for verification
            print("\n📋 Current users in database:")
            users = User.query.all()
            for user in users:
                status = "✅" if user.is_verified and user.is_active else "❌"
                print(f"  {status} {user.phone_number} - {user.name} ({user.role})")
                
        except Exception as e:
            print(f"❌ Error: {e}")
            db.session.rollback()

if __name__ == '__main__':
    print("🚀 Initializing Flask app...")
    fix_postman_users()
    print("✅ Done!")