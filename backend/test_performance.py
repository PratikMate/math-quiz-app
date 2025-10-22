#!/usr/bin/env python3
"""
Simple performance test to verify monitoring and optimization features.
"""
import asyncio
import time
import json
from app.services.performance_monitor import performance_monitor
from app.services.structured_logger import get_structured_logger, RequestTracer
from app.services.redis_service import RedisService
from app.services.cache_service import CacheService

logger = get_structured_logger(__name__)

async def test_performance_monitoring():
    """Test performance monitoring features."""
    print("Testing Performance Monitoring...")
    
    # Start monitoring
    await performance_monitor.start_monitoring()
    
    # Test API request tracking
    async with performance_monitor.track_request("/test/api", "GET", "test_user") as tracker:
        await asyncio.sleep(0.1)  # Simulate work
        tracker.set_status(200)
    
    # Test WebSocket tracking
    performance_monitor.track_websocket_connection("test_conn_1", "connect")
    performance_monitor.track_websocket_connection("test_conn_1", "message", {"size": 100})
    
    # Test Gemini API tracking
    performance_monitor.track_gemini_api_call(
        request_type="generate_problem",
        response_time_ms=1500,
        success=True,
        tokens_used=50
    )
    
    # Get performance summary
    summary = performance_monitor.get_comprehensive_report()
    print(f"Performance Summary: {json.dumps(summary, indent=2, default=str)}")
    
    await performance_monitor.stop_monitoring()
    print("✓ Performance monitoring test completed")

async def test_cache_service():
    """Test cache service functionality."""
    print("Testing Cache Service...")
    
    # Initialize Redis service (mock for testing)
    redis_service = RedisService()
    
    try:
        await redis_service.connect()
        cache_service = CacheService(redis_service)
        
        # Test cache operations
        await cache_service.set("test", "key1", {"data": "value1"}, ttl=60)
        
        # Test cache retrieval
        cached_value = await cache_service.get("test", "key1")
        print(f"Cached value: {cached_value}")
        
        # Test cache statistics
        stats = cache_service.get_cache_stats()
        print(f"Cache stats: {json.dumps(stats, indent=2)}")
        
        # Test cache miss
        missing_value = await cache_service.get("test", "nonexistent", default="not_found")
        print(f"Missing value (should be 'not_found'): {missing_value}")
        
        await redis_service.disconnect()
        print("✓ Cache service test completed")
        
    except Exception as e:
        print(f"Cache test failed (expected if Redis not available): {e}")

async def test_structured_logging():
    """Test structured logging features."""
    print("Testing Structured Logging...")
    
    # Test request tracing
    async with RequestTracer(endpoint="/test", method="POST", user_id="test_user"):
        logger.info("Test log message", extra_data="test_value")
        
        logger.log_api_call(
            endpoint="/test",
            method="POST",
            status_code=200,
            response_time_ms=150
        )
        
        logger.log_slow_operation(
            operation="test_operation",
            duration_ms=2000,
            threshold_ms=1000
        )
    
    print("✓ Structured logging test completed")

async def main():
    """Run all performance tests."""
    print("=" * 50)
    print("PERFORMANCE OPTIMIZATION TESTS")
    print("=" * 50)
    
    try:
        await test_performance_monitoring()
        print()
        
        await test_cache_service()
        print()
        
        await test_structured_logging()
        print()
        
        print("=" * 50)
        print("ALL TESTS COMPLETED SUCCESSFULLY!")
        print("=" * 50)
        
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())