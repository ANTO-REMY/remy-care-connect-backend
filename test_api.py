#!/usr/bin/env python3
"""
Test script to verify backend API connectivity and authentication
"""
import requests
import json

API_BASE = "http://localhost:5001/api/v1"

def test_api():
    print("🧪 Testing RemyCareConnect API...")
    print("=" * 50)
    
    # Test 1: Health check
    print("1. Testing health endpoint...")
    try:
        response = requests.get(f"{API_BASE}/health")
        if response.status_code == 200:
            print("   ✅ Health check passed")
        else:
            print(f"   ❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Health check error: {e}")
        return False
    
    # Test 2: Registration
    print("2. Testing user registration...")
    registration_data = {
        "phone_number": "+254700000999",
        "name": "Test User",
        "pin": "test123",
        "role": "mother"
    }
    
    try:
        response = requests.post(f"{API_BASE}/auth/register", 
                               json=registration_data,
                               headers={"Content-Type": "application/json"})
        
        if response.status_code in [201, 409]:  # 201 = created, 409 = already exists
            print("   ✅ Registration endpoint working")
            if response.status_code == 201:
                data = response.json()
                print(f"      OTP Code (for testing): {data.get('otp_code', 'N/A')}")
        else:
            print(f"   ❌ Registration failed: {response.status_code}")
            print(f"      Response: {response.text}")
    except Exception as e:
        print(f"   ❌ Registration error: {e}")
    
    # Test 3: Login with demo user
    print("3. Testing login with demo user...")
    login_data = {
        "phone_number": "+254700000001",
        "pin": "demo123"
    }
    
    try:
        response = requests.post(f"{API_BASE}/auth/login",
                               json=login_data, 
                               headers={"Content-Type": "application/json"})
        
        if response.status_code == 200:
            print("   ✅ Login successful")
            data = response.json()
            print(f"      User: {data.get('user', {}).get('name', 'Unknown')}")
            print(f"      Role: {data.get('user', {}).get('role', 'Unknown')}")
        else:
            print(f"   ❌ Login failed: {response.status_code}")
            print(f"      Response: {response.text}")
    except Exception as e:
        print(f"   ❌ Login error: {e}")
    
    print("\n🎯 API testing completed!")
    return True

if __name__ == "__main__":
    test_api()