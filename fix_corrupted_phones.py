#!/usr/bin/env python3
"""
Fix corrupted phone numbers in the database
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from app import create_app
from models import db, User
import re

def fix_corrupted_phones():
    """Fix phone numbers that were incorrectly normalized"""
    app = create_app()
    
    with app.app_context():
        try:
            print("🔧 Fixing corrupted phone numbers...")
            
            users = User.query.all()
            fixed_count = 0
            
            for user in users:
                phone = user.phone_number
                original_phone = phone
                
                # Fix corrupted phone numbers
                if phone.startswith('+25400000'):
                    # These should be +254700000xxx
                    phone = '+254700000' + phone[9:]
                    print(f"📞 Fixing corrupted phone: {original_phone} → {phone}")
                    user.phone_number = phone
                    fixed_count += 1
                elif phone.startswith('+25459396'):
                    # This should be +254759396xxx
                    phone = '+254759396' + phone[10:]
                    print(f"📞 Fixing corrupted phone: {original_phone} → {phone}")
                    user.phone_number = phone
                    fixed_count += 1
            
            if fixed_count > 0:
                db.session.commit()
                print(f"✅ Fixed {fixed_count} phone numbers")
            else:
                print("✅ All phone numbers are correct")
                
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
    fix_corrupted_phones()
    print("✅ Done!")