"""
Database connection and session management.
"""
import os
import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class DatabaseManager:
    """
    Manages database connections and sessions with connection pooling.
    """
    
    def __init__(self):
        self.engine = None
        self.async_session_maker = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize database connection and session maker."""
        if self._initialized:
            return
        
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            raise ValueError("DATABASE_URL environment variable is required")
        
        # Convert postgres:// to postgresql+asyncpg:// if needed
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql+asyncpg://', 1)
        elif database_url.startswith('postgresql://') and not database_url.startswith('postgresql+asyncpg://'):
            # Assume it's a standard postgresql URL and add asyncpg driver
            database_url = database_url.replace('postgresql://', 'postgresql+asyncpg://', 1)
        
        # Create async engine with appropriate configuration for database type
        engine_kwargs = {
            'echo': os.getenv('DATABASE_ECHO', 'false').lower() == 'true'
        }
        
        # Add connection pooling parameters only for PostgreSQL
        if database_url.startswith('postgresql'):
            engine_kwargs.update({
                'pool_size': int(os.getenv('DATABASE_POOL_SIZE', '10')),
                'max_overflow': int(os.getenv('DATABASE_MAX_OVERFLOW', '20')),
                'pool_timeout': int(os.getenv('DATABASE_POOL_TIMEOUT', '30')),
                'pool_recycle': int(os.getenv('DATABASE_POOL_RECYCLE', '3600')),
                # Use NullPool for Heroku to avoid connection limits
                'poolclass': NullPool if os.getenv('HEROKU') else None
            })
        
        self.engine = create_async_engine(database_url, **engine_kwargs)
        
        # Create session maker
        self.async_session_maker = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        self._initialized = True
        logger.info("Database connection initialized successfully")
    
    async def close(self):
        """Close database connections."""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database connections closed")
    
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get an async database session.
        
        Yields:
            AsyncSession: Database session
        """
        if not self._initialized:
            await self.initialize()
        
        async with self.async_session_maker() as session:
            try:
                yield session
            except Exception as e:
                await session.rollback()
                logger.error(f"Database session error: {e}")
                raise
            finally:
                await session.close()
    
    async def create_tables(self):
        """Create all database tables."""
        if not self._initialized:
            await self.initialize()
        
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("Database tables created successfully")
    
    async def health_check(self) -> dict:
        """
        Check database connection health.
        
        Returns:
            dict: Health status information
        """
        try:
            if not self._initialized:
                return {"status": "not_initialized", "error": "Database not initialized"}
            
            from sqlalchemy import text
            async with self.async_session_maker() as session:
                result = await session.execute(text("SELECT 1"))
                result.fetchone()
                
            return {
                "status": "healthy",
                "engine_pool_size": self.engine.pool.size() if hasattr(self.engine.pool, 'size') else None,
                "engine_checked_in": self.engine.pool.checkedin() if hasattr(self.engine.pool, 'checkedin') else None,
                "engine_checked_out": self.engine.pool.checkedout() if hasattr(self.engine.pool, 'checkedout') else None
            }
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {"status": "unhealthy", "error": str(e)}


# Global database manager instance
db_manager = DatabaseManager()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function to get database session.
    
    Yields:
        AsyncSession: Database session
    """
    async for session in db_manager.get_session():
        yield session