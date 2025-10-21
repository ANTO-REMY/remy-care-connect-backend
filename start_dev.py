#!/usr/bin/env python3
"""
Development startup script for RemyCareConnect Backend

This script:
1. Starts PostgreSQL and Redis via Docker Compose
2. Starts the Flask development server locally on port 5001
3. Provides clear logging and status information
"""

import subprocess
import sys
import time
import requests
from app import create_app

def check_docker_services():
    """Check if Docker services are running"""
    try:
        result = subprocess.run(['docker-compose', 'ps'], 
                              capture_output=True, text=True, cwd='.')
        return 'db' in result.stdout and 'redis' in result.stdout
    except:
        return False

def start_docker_services():
    """Start Docker services (DB and Redis)"""
    print("🐳 Starting Docker services (PostgreSQL + Redis)...")
    try:
        subprocess.run(['docker-compose', 'up', '-d'], cwd='.')
        print("✅ Docker services started")
        return True
    except Exception as e:
        print(f"❌ Failed to start Docker services: {e}")
        return False

def wait_for_services():
    """Wait for services to be healthy"""
    print("⏳ Waiting for services to be ready...")
    max_attempts = 30
    for i in range(max_attempts):
        try:
            # Check PostgreSQL
            result = subprocess.run(['docker-compose', 'exec', '-T', 'db', 'pg_isready', '-U', 'postgres'], 
                                  capture_output=True, cwd='.')
            if result.returncode == 0:
                print("✅ PostgreSQL is ready")
                break
        except:
            pass
        
        if i == max_attempts - 1:
            print("❌ Services didn't start in time")
            return False
        
        time.sleep(2)
        print(f"   Attempt {i+1}/{max_attempts}...")
    
    return True

def start_flask_server():
    """Start Flask development server"""
    print("\n🚀 Starting Flask development server on port 5001...")
    print("📊 Database: PostgreSQL (Docker)")
    print("🔄 Cache: Redis (Docker)")  
    print("🌐 Backend: Local Flask development server")
    print("🔗 Health check: http://localhost:5001/api/v1/health")
    print("📝 Postman collection configured for port 5001")
    print("\n💡 Quick start alternative: python -c \"from app import create_app; create_app().run(host='0.0.0.0', port=5001, debug=True)\"")
    print("\n" + "="*50)
    
    app = create_app()
    app.run(host='0.0.0.0', port=5001, debug=True)

if __name__ == '__main__':
    print("🎯 RemyCareConnect Development Server Startup")
    print("="*50)
    
    # Check if services are already running
    if not check_docker_services():
        if not start_docker_services():
            sys.exit(1)
    else:
        print("✅ Docker services already running")
    
    # Wait for services to be ready
    if not wait_for_services():
        sys.exit(1)
    
    # Start Flask server
    start_flask_server()
