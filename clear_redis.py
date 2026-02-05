#!/usr/bin/env python3
"""
Quick script to clear Redis cache
Run this if you encounter session-related errors
"""
import redis
import os
from dotenv import load_dotenv

load_dotenv()

def clear_redis():
    """Clear all Redis cache"""
    try:
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        redis_client = redis.StrictRedis.from_url(redis_url, decode_responses=True)
        redis_client.flushall()
        print("✅ Redis cache cleared successfully!")
        print(f"   Connected to: {redis_url}")
        return True
    except Exception as e:
        print(f"❌ Error clearing Redis: {e}")
        print("\nAlternative: Run this command manually:")
        print("   docker exec backend-redis-1 redis-cli FLUSHALL")
        return False

if __name__ == '__main__':
    print("🔧 Clearing Redis cache...")
    clear_redis()
