#!/usr/bin/env python3
"""
Test the login API endpoint directly
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from app import create_app
from models import db, User
import requests
import json

def test_login_api():
    """Test the login API endpoint"""
    try:
        # Test the API endpoint directly
        url = "http://localhost:5001/api/v1/auth/login"
        data = {
            "phone_number": "0700000001",
            "pin": "1234"
        }
        
        print(f"🔗 Testing login API: {url}")
        print(f"📤 Request data: {data}")
        
        response = requests.post(url, json=data, headers={"Content-Type": "application/json"})
        
        print(f"📥 Response status: {response.status_code}")
        print(f"📥 Response text: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Login successful!")
            print(f"User: {result.get('user', {})}")
        else:
            print("❌ Login failed")
            
    except Exception as e:
        print(f"❌ Error testing API: {e}")

def check_users():
    """Check what users exist in database"""
    app = create_app()
    
    with app.app_context():
        try:
            print("👥 Current users in database:")
            users = User.query.all()
            for user in users:
                status = "✅" if user.is_verified and user.is_active else "❌"
                print(f"  {status} {user.phone_number} - {user.name} ({user.role}) - PIN hash: {user.pin_hash[:20]}...")
                
        except Exception as e:
            print(f"❌ Error checking users: {e}")

if __name__ == '__main__':
    print("🚀 Testing login functionality...")
    check_users()
    print("\n" + "="*50)
    test_login_api()
    print("✅ Done!")