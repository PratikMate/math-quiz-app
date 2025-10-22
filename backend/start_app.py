#!/usr/bin/env python3
"""
Safe application startup script.
Checks Redis availability before starting the main application.
"""
import subprocess
import sys
import os

def main():
    print("🚀 Starting Competitive Math Quiz Backend...")
    
    # Check if Redis is running
    print("📡 Checking Redis connection...")
    result = subprocess.run([sys.executable, "check_redis.py"], capture_output=True, text=True)
    
    if result.returncode != 0:
        print("\n❌ Startup failed - Redis is not available")
        print(result.stdout)
        print("\nTo start Redis:")
        print("  redis-server --daemonize yes")
        print("\nOr install Redis if not installed:")
        print("  brew install redis  # macOS")
        print("  sudo apt install redis-server  # Ubuntu")
        sys.exit(1)
    
    print(result.stdout.strip())
    
    # Start the main application
    print("\n🎯 Starting FastAPI application...")
    try:
        subprocess.run([sys.executable, "main.py"], check=True)
    except KeyboardInterrupt:
        print("\n👋 Application stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Application failed to start: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
