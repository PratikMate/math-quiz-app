"""
Health check utilities for production monitoring.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter
from pydantic import BaseModel

from config import settings
from app.services.redis_service import RedisService
from app.services.database_service import DatabaseService

logger = logging.getLogger(__name__)

class HealthStatus(BaseModel):
    """Health check response model."""
    status: str
    timestamp: str
    version: str = "1.0.0"
    environment: str
    services: Dict[str, Any]
    uptime_seconds: Optional[float] = None

class ServiceHealth(BaseModel):
    """Individual service health status."""
    status: str
    response_time_ms: Optional[float] = None
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

# Track application start time
app_start_time = datetime.utcnow()

# Create health check router
health_router = APIRouter(prefix="/health", tags=["health"])

async def check_service_health(service_name: str, check_func) -> ServiceHealth:
    """Check health of an individual service."""
    start_time = datetime.utcnow()
    
    try:
        result = await check_func()
        end_time = datetime.utcnow()
        response_time = (end_time - start_time).total_seconds() * 1000
        
        return ServiceHealth(
            status="healthy",
            response_time_ms=response_time,
            details=result if isinstance(result, dict) else None
        )
    
    except Exception as e:
        end_time = datetime.utcnow()
        response_time = (end_time - start_time).total_seconds() * 1000
        
        logger.error(f"Health check failed for {service_name}: {e}")
        
        return ServiceHealth(
            status="unhealthy",
            response_time_ms=response_time,
            error=str(e)
        )

async def check_redis_health() -> Dict[str, Any]:
    """Check Redis connection and basic operations."""
    redis_service = RedisService()
    
    # Test basic Redis operations
    test_key = "health_check_test"
    test_value = "ok"
    
    await redis_service.redis.set(test_key, test_value, ex=10)
    retrieved_value = await redis_service.redis.get(test_key)
    await redis_service.redis.delete(test_key)
    
    if retrieved_value != test_value:
        raise Exception("Redis read/write test failed")
    
    # Get Redis info
    info = await redis_service.redis.info()
    
    return {
        "connected_clients": info.get("connected_clients", 0),
        "used_memory_human": info.get("used_memory_human", "unknown"),
        "redis_version": info.get("redis_version", "unknown")
    }

async def check_database_health() -> Dict[str, Any]:
    """Check database connection and basic operations."""
    db_service = DatabaseService()
    
    # Test database connection with a simple query
    async with db_service.get_session() as session:
        result = await session.execute("SELECT 1 as test")
        row = result.fetchone()
        
        if not row or row[0] != 1:
            raise Exception("Database query test failed")
    
    # Get database stats
    stats = await db_service.get_system_stats()
    
    return {
        "connection_pool_size": stats.get("pool_size", "unknown"),
        "active_connections": stats.get("active_connections", "unknown"),
        "database_size": stats.get("database_size", "unknown")
    }

@health_router.get("/", response_model=HealthStatus)
async def health_check():
    """Comprehensive health check endpoint."""
    
    # Calculate uptime
    uptime = (datetime.utcnow() - app_start_time).total_seconds()
    
    # Check all services
    services = {}
    
    # Check Redis
    services["redis"] = await check_service_health("redis", check_redis_health)
    
    # Check Database
    services["database"] = await check_service_health("database", check_database_health)
    
    # Determine overall status
    overall_status = "healthy"
    for service_health in services.values():
        if service_health.status != "healthy":
            overall_status = "degraded"
            break
    
    return HealthStatus(
        status=overall_status,
        timestamp=datetime.utcnow().isoformat(),
        environment=settings.ENVIRONMENT if hasattr(settings, 'ENVIRONMENT') else 'unknown',
        services=services,
        uptime_seconds=uptime
    )

@health_router.get("/live")
async def liveness_check():
    """Simple liveness check for Kubernetes/container orchestration."""
    return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}

@health_router.get("/ready")
async def readiness_check():
    """Readiness check - ensures all dependencies are available."""
    
    # Quick check of critical services
    try:
        # Check Redis
        redis_service = RedisService()
        await redis_service.redis.ping()
        
        # Check Database
        db_service = DatabaseService()
        async with db_service.get_session() as session:
            await session.execute("SELECT 1")
        
        return {
            "status": "ready",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return {
            "status": "not_ready",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

@health_router.get("/metrics")
async def metrics():
    """Basic metrics endpoint for monitoring."""
    
    uptime = (datetime.utcnow() - app_start_time).total_seconds()
    
    # Get service metrics
    metrics_data = {
        "uptime_seconds": uptime,
        "timestamp": datetime.utcnow().isoformat(),
        "environment": settings.ENVIRONMENT if hasattr(settings, 'ENVIRONMENT') else 'unknown',
        "version": "1.0.0"
    }
    
    try:
        # Redis metrics
        redis_service = RedisService()
        redis_info = await redis_service.redis.info()
        metrics_data["redis"] = {
            "connected_clients": redis_info.get("connected_clients", 0),
            "used_memory": redis_info.get("used_memory", 0),
            "total_commands_processed": redis_info.get("total_commands_processed", 0)
        }
    except Exception as e:
        metrics_data["redis"] = {"error": str(e)}
    
    try:
        # Database metrics
        db_service = DatabaseService()
        db_stats = await db_service.get_system_stats()
        metrics_data["database"] = db_stats
    except Exception as e:
        metrics_data["database"] = {"error": str(e)}
    
    return metrics_data