#!/usr/bin/env python3
"""
PostgreSQL database setup script.
Creates database and user for the competitive math quiz application.
"""
import asyncio
import asyncpg
import sys
import os
from getpass import getpass

async def setup_database():
    """Set up PostgreSQL database for the application."""
    
    print("🐘 PostgreSQL Database Setup")
    print("=" * 40)
    
    # Get connection details
    host = input("PostgreSQL host (default: localhost): ").strip() or "localhost"
    port = input("PostgreSQL port (default: 5432): ").strip() or "5432"
    admin_user = input("PostgreSQL admin user (default: postgres): ").strip() or "postgres"
    admin_password = getpass("PostgreSQL admin password: ")
    
    # Database details
    db_name = "competitive_math_quiz"
    db_user = "quiz_user"
    db_password = input("Password for quiz_user (default: password): ").strip() or "password"
    
    try:
        # Connect as admin
        print(f"\n📡 Connecting to PostgreSQL at {host}:{port}...")
        conn = await asyncpg.connect(
            host=host,
            port=port,
            user=admin_user,
            password=admin_password,
            database="postgres"
        )
        
        # Check if database exists
        db_exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", db_name
        )
        
        if db_exists:
            print(f"⚠️  Database '{db_name}' already exists")
            overwrite = input("Do you want to recreate it? (y/N): ").strip().lower()
            if overwrite == 'y':
                await conn.execute(f"DROP DATABASE {db_name}")
                print(f"🗑️  Dropped existing database '{db_name}'")
            else:
                print("Skipping database creation")
                await conn.close()
                return
        
        # Check if user exists
        user_exists = await conn.fetchval(
            "SELECT 1 FROM pg_user WHERE usename = $1", db_user
        )
        
        if user_exists:
            print(f"⚠️  User '{db_user}' already exists")
            await conn.execute(f"ALTER USER {db_user} WITH PASSWORD '{db_password}'")
            print(f"🔑 Updated password for user '{db_user}'")
        else:
            # Create user
            await conn.execute(f"CREATE USER {db_user} WITH PASSWORD '{db_password}'")
            print(f"👤 Created user '{db_user}'")
        
        # Create database
        await conn.execute(f"CREATE DATABASE {db_name} OWNER {db_user}")
        print(f"🗄️  Created database '{db_name}'")
        
        # Grant privileges
        await conn.execute(f"GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {db_user}")
        print(f"🔐 Granted privileges to '{db_user}'")
        
        await conn.close()
        
        # Test connection with new user
        print(f"\n🧪 Testing connection as '{db_user}'...")
        test_conn = await asyncpg.connect(
            host=host,
            port=port,
            user=db_user,
            password=db_password,
            database=db_name
        )
        
        # Create a test table to verify permissions
        await test_conn.execute("""
            CREATE TABLE IF NOT EXISTS test_table (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        await test_conn.execute("DROP TABLE test_table")
        await test_conn.close()
        
        print("✅ Database setup completed successfully!")
        
        # Generate connection string
        connection_string = f"postgresql+asyncpg://{db_user}:{db_password}@{host}:{port}/{db_name}"
        
        print(f"\n📝 Add this to your .env file:")
        print(f"DATABASE_URL={connection_string}")
        
        # Update .env file if it exists
        env_file = ".env"
        if os.path.exists(env_file):
            update_env = input(f"\nUpdate {env_file} file? (Y/n): ").strip().lower()
            if update_env != 'n':
                # Read current .env
                with open(env_file, 'r') as f:
                    lines = f.readlines()
                
                # Update DATABASE_URL line
                updated = False
                for i, line in enumerate(lines):
                    if line.startswith('DATABASE_URL='):
                        lines[i] = f"DATABASE_URL={connection_string}\n"
                        updated = True
                        break
                
                if not updated:
                    lines.append(f"DATABASE_URL={connection_string}\n")
                
                # Write back
                with open(env_file, 'w') as f:
                    f.writelines(lines)
                
                print(f"✅ Updated {env_file}")
        
    except Exception as e:
        print(f"❌ Error setting up database: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(setup_database())
