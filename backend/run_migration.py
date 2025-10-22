#!/usr/bin/env python3
"""
Script to run database migrations for performance optimization.
"""
import asyncio
import os
import sys
from alembic.config import Config
from alembic import command

def run_migrations():
    """Run Alembic migrations."""
    try:
        # Get the directory containing this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Path to alembic.ini
        alembic_cfg_path = os.path.join(script_dir, "alembic.ini")
        
        if not os.path.exists(alembic_cfg_path):
            print(f"Error: alembic.ini not found at {alembic_cfg_path}")
            return False
        
        # Create Alembic configuration
        alembic_cfg = Config(alembic_cfg_path)
        
        # Set the script location
        alembic_cfg.set_main_option("script_location", os.path.join(script_dir, "alembic"))
        
        print("Running database migrations...")
        
        # Run migrations
        command.upgrade(alembic_cfg, "head")
        
        print("Migrations completed successfully!")
        return True
        
    except Exception as e:
        print(f"Error running migrations: {e}")
        return False

if __name__ == "__main__":
    success = run_migrations()
    sys.exit(0 if success else 1)