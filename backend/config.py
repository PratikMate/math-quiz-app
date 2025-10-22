"""
Production configuration for Competitive Math Quiz application.
Handles environment variables, logging, and security settings.
"""

import os
import logging
import sys
from typing import List, Optional
from pydantic import validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Settings(BaseSettings):
    """Application settings with validation and defaults."""
    
    # Server Configuration
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    DEBUG: bool = False
    
    # CORS Configuration
    CORS_ORIGINS: str = "*"
    
    # Database Configuration
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    
    # Redis Configuration
    REDIS_URL: str
    REDIS_POOL_SIZE: int = 10
    REDIS_RETRY_ON_TIMEOUT: bool = True
    
    # API Keys
    GEMINI_API_KEY: str
    SECRET_KEY: str
    
    # Security Settings
    API_KEY_ROTATION_DAYS: int = 30
    MAX_CONCURRENT_USERS: int = 100
    RATE_LIMIT_PER_MINUTE: int = 60
    
    # Logging Configuration
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Performance Settings
    WEBSOCKET_PING_TIMEOUT: int = 60
    WEBSOCKET_PING_INTERVAL: int = 25
    SUBMISSION_TIMEOUT_SECONDS: int = 30
    
    # Question Prefetch Configuration
    PREFETCH_BATCH_SIZE: int = 20
    PREFETCH_MIN_THRESHOLD: int = 5
    PREFETCH_ENABLED: bool = True
    
    @validator('CORS_ORIGINS')
    def parse_cors_origins(cls, v: str) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        if v == "*":
            return ["*"]
        return [origin.strip() for origin in v.split(",") if origin.strip()]
    
    @validator('DATABASE_URL')
    def validate_database_url(cls, v: str) -> str:
        """Validate database URL format."""
        if not v:
            raise ValueError("DATABASE_URL is required")
        # Allow SQLite for development, PostgreSQL for production
        valid_prefixes = ('postgresql://', 'postgresql+asyncpg://', 'sqlite://', 'sqlite+aiosqlite://')
        if not v.startswith(valid_prefixes):
            raise ValueError("DATABASE_URL must be a PostgreSQL or SQLite URL")
        return v
    
    @validator('REDIS_URL')
    def validate_redis_url(cls, v: str) -> str:
        """Validate Redis URL format."""
        if not v:
            raise ValueError("REDIS_URL is required")
        if not v.startswith(('redis://', 'rediss://')):
            raise ValueError("REDIS_URL must be a Redis URL")
        return v
    
    @validator('GEMINI_API_KEY')
    def validate_gemini_api_key(cls, v: str) -> str:
        """Validate Gemini API key."""
        # Allow placeholder for development, require real key for production
        if not v:
            raise ValueError("GEMINI_API_KEY must be set")
        # Only enforce real API key in production
        if os.getenv('ENVIRONMENT', '').lower() == 'production' and v == "your_gemini_api_key_here":
            raise ValueError("GEMINI_API_KEY must be set to a valid API key in production")
        return v
    
    @validator('SECRET_KEY')
    def validate_secret_key(cls, v: str) -> str:
        """Validate secret key."""
        if not v:
            raise ValueError("SECRET_KEY must be set")
        # Only enforce length requirement in production
        if os.getenv('ENVIRONMENT', '').lower() == 'production' and len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long in production")
        return v
    
    @validator('LOG_LEVEL')
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of: {valid_levels}")
        return v.upper()
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# Global settings instance
settings = Settings()

def setup_logging():
    """Configure application logging for production."""
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL),
        format=settings.LOG_FORMAT,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )
    
    # Configure specific loggers
    loggers = {
        'uvicorn': logging.INFO,
        'uvicorn.error': logging.INFO,
        'uvicorn.access': logging.WARNING if not settings.DEBUG else logging.INFO,
        'socketio': logging.WARNING,
        'engineio': logging.WARNING,
        'redis': logging.WARNING,
        'sqlalchemy.engine': logging.WARNING if not settings.DEBUG else logging.INFO,
    }
    
    for logger_name, level in loggers.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
    
    # Disable debug logging in production
    if not settings.DEBUG:
        logging.getLogger('asyncio').setLevel(logging.WARNING)
        logging.getLogger('aioredis').setLevel(logging.WARNING)

def get_cors_origins() -> List[str]:
    """Get CORS origins for the application."""
    return settings.CORS_ORIGINS

def is_production() -> bool:
    """Check if running in production environment."""
    return not settings.DEBUG and os.getenv('ENVIRONMENT', '').lower() == 'production'

def get_database_config() -> dict:
    """Get database configuration."""
    return {
        'url': settings.DATABASE_URL,
        'pool_size': settings.DATABASE_POOL_SIZE,
        'max_overflow': settings.DATABASE_MAX_OVERFLOW,
        'echo': settings.DEBUG,
    }

def get_redis_config() -> dict:
    """Get Redis configuration."""
    return {
        'url': settings.REDIS_URL,
        'max_connections': settings.REDIS_POOL_SIZE,
        'retry_on_timeout': settings.REDIS_RETRY_ON_TIMEOUT,
        'socket_keepalive': True,
        'socket_keepalive_options': {},
    }

def get_websocket_config() -> dict:
    """Get WebSocket configuration."""
    return {
        'ping_timeout': settings.WEBSOCKET_PING_TIMEOUT,
        'ping_interval': settings.WEBSOCKET_PING_INTERVAL,
        'cors_allowed_origins': get_cors_origins(),
        'async_mode': 'asgi',
    }

# Security utilities
def mask_sensitive_data(data: str, visible_chars: int = 4) -> str:
    """Mask sensitive data for logging."""
    if len(data) <= visible_chars:
        return "*" * len(data)
    return data[:visible_chars] + "*" * (len(data) - visible_chars)

def log_startup_info():
    """Log application startup information."""
    logger = logging.getLogger(__name__)
    
    logger.info("=== Competitive Math Quiz Server Starting ===")
    logger.info(f"Environment: {'Production' if is_production() else 'Development'}")
    logger.info(f"Host: {settings.HOST}:{settings.PORT}")
    logger.info(f"Debug Mode: {settings.DEBUG}")
    logger.info(f"Log Level: {settings.LOG_LEVEL}")
    logger.info(f"CORS Origins: {settings.CORS_ORIGINS}")
    logger.info(f"Max Concurrent Users: {settings.MAX_CONCURRENT_USERS}")
    logger.info(f"Database: {mask_sensitive_data(settings.DATABASE_URL, 20)}")
    logger.info(f"Redis: {mask_sensitive_data(settings.REDIS_URL, 15)}")
    logger.info(f"Gemini API Key: {mask_sensitive_data(settings.GEMINI_API_KEY)}")
    logger.info("=== Configuration Loaded Successfully ===")