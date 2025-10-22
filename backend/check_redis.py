#!/usr/bin/env python3
"""
Redis connection check script.
Run this before starting the main application to ensure Redis is available.
"""
import redis
import sys
import logging

def check_redis_connection():
    """Check if Redis is running and accessible."""
    try:
        # Try to connect to Redis
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        
        # Test the connection
        r.ping()
        
        print("✅ Redis is running and accessible")
        return True
        
    except redis.ConnectionError as e:
        print("❌ Redis connection failed:")
        print(f"   Error: {e}")
        print("   Please start Redis server:")
        print("   redis-server --daemonize yes")
        return False
        
    except Exception as e:
        print(f"❌ Unexpected error checking Redis: {e}")
        return False

if __name__ == "__main__":
    if not check_redis_connection():
        sys.exit(1)
    print("Redis check passed - ready to start application")
