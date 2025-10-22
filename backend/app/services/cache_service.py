"""
Caching service for frequently accessed data with intelligent cache management.
"""
import asyncio
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Callable, Union
from dataclasses import dataclass
from collections import defaultdict
import hashlib

from .redis_service import RedisService
from .structured_logger import get_structured_logger

logger = get_structured_logger(__name__)


@dataclass
class CacheEntry:
    """Represents a cached entry with metadata."""
    key: str
    value: Any
    created_at: datetime
    expires_at: Optional[datetime]
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    size_bytes: int = 0


class CacheService:
    """
    Intelligent caching service with multiple cache layers and strategies.
    
    Provides in-memory caching with Redis fallback, cache warming,
    and intelligent eviction policies.
    """
    
    def __init__(self, redis_service: RedisService, max_memory_cache_size: int = 1000):
        """
        Initialize cache service.
        
        Args:
            redis_service: Redis service instance
            max_memory_cache_size: Maximum number of items in memory cache
        """
        self.redis_service = redis_service
        self.max_memory_cache_size = max_memory_cache_size
        
        # In-memory cache (L1)
        self.memory_cache: Dict[str, CacheEntry] = {}
        
        # Cache statistics
        self.stats = {
            'hits': 0,
            'misses': 0,
            'memory_hits': 0,
            'redis_hits': 0,
            'evictions': 0,
            'cache_size': 0
        }
        
        # Cache key prefixes
        self.CACHE_PREFIX = "cache:"
        self.LEADERBOARD_KEY = "leaderboard"
        self.USER_STATS_PREFIX = "user_stats"
        self.PROBLEM_STATS_PREFIX = "problem_stats"
        self.SYSTEM_STATS_KEY = "system_stats"
        
        # Default TTL values (in seconds)
        self.DEFAULT_TTL = 300  # 5 minutes
        self.LEADERBOARD_TTL = 60  # 1 minute
        self.USER_STATS_TTL = 180  # 3 minutes
        self.SYSTEM_STATS_TTL = 30  # 30 seconds
        
        # Cache warming tasks
        self.warming_tasks: Dict[str, asyncio.Task] = {}
    
    def _generate_cache_key(self, namespace: str, identifier: str) -> str:
        """Generate a standardized cache key."""
        return f"{self.CACHE_PREFIX}{namespace}:{identifier}"
    
    def _calculate_size(self, value: Any) -> int:
        """Calculate approximate size of cached value in bytes."""
        try:
            if isinstance(value, (str, bytes)):
                return len(value.encode('utf-8') if isinstance(value, str) else value)
            elif isinstance(value, (dict, list)):
                return len(json.dumps(value, default=str).encode('utf-8'))
            else:
                return len(str(value).encode('utf-8'))
        except Exception:
            return 100  # Default estimate
    
    def _should_evict_from_memory(self) -> bool:
        """Check if memory cache needs eviction."""
        return len(self.memory_cache) >= self.max_memory_cache_size
    
    def _evict_from_memory_cache(self):
        """Evict least recently used items from memory cache."""
        if not self.memory_cache:
            return
        
        # Sort by last accessed time (LRU)
        sorted_entries = sorted(
            self.memory_cache.items(),
            key=lambda x: x[1].last_accessed or x[1].created_at
        )
        
        # Remove oldest 20% of entries
        evict_count = max(1, len(sorted_entries) // 5)
        
        for i in range(evict_count):
            key, _ = sorted_entries[i]
            del self.memory_cache[key]
            self.stats['evictions'] += 1
        
        logger.debug(f"Evicted {evict_count} entries from memory cache")
    
    async def get(
        self,
        namespace: str,
        identifier: str,
        default: Any = None,
        ttl: Optional[int] = None
    ) -> Any:
        """
        Get value from cache with multi-layer lookup.
        
        Args:
            namespace: Cache namespace
            identifier: Cache identifier
            default: Default value if not found
            ttl: TTL for Redis cache if not found in memory
            
        Returns:
            Cached value or default
        """
        cache_key = self._generate_cache_key(namespace, identifier)
        start_time = time.time()
        
        try:
            # Check memory cache first (L1)
            if cache_key in self.memory_cache:
                entry = self.memory_cache[cache_key]
                
                # Check if expired
                if entry.expires_at and datetime.utcnow() > entry.expires_at:
                    del self.memory_cache[cache_key]
                else:
                    # Update access statistics
                    entry.access_count += 1
                    entry.last_accessed = datetime.utcnow()
                    
                    self.stats['hits'] += 1
                    self.stats['memory_hits'] += 1
                    
                    duration_ms = (time.time() - start_time) * 1000
                    logger.debug(
                        f"Memory cache hit: {namespace}:{identifier}",
                        cache_key=cache_key,
                        duration_ms=duration_ms,
                        access_count=entry.access_count
                    )
                    
                    return entry.value
            
            # Check Redis cache (L2)
            redis_key = cache_key
            cached_data = await self.redis_service.redis_client.get(redis_key)
            
            if cached_data:
                try:
                    value = json.loads(cached_data)
                    
                    # Store in memory cache for faster future access
                    await self._store_in_memory_cache(cache_key, value, ttl)
                    
                    self.stats['hits'] += 1
                    self.stats['redis_hits'] += 1
                    
                    duration_ms = (time.time() - start_time) * 1000
                    logger.debug(
                        f"Redis cache hit: {namespace}:{identifier}",
                        cache_key=cache_key,
                        duration_ms=duration_ms
                    )
                    
                    return value
                    
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON in cache key: {cache_key}")
            
            # Cache miss
            self.stats['misses'] += 1
            
            duration_ms = (time.time() - start_time) * 1000
            logger.debug(
                f"Cache miss: {namespace}:{identifier}",
                cache_key=cache_key,
                duration_ms=duration_ms
            )
            
            return default
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                f"Cache get error: {namespace}:{identifier}",
                exception=e,
                cache_key=cache_key,
                duration_ms=duration_ms
            )
            return default
    
    async def set(
        self,
        namespace: str,
        identifier: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set value in cache with multi-layer storage.
        
        Args:
            namespace: Cache namespace
            identifier: Cache identifier
            value: Value to cache
            ttl: Time to live in seconds
            
        Returns:
            True if successful, False otherwise
        """
        cache_key = self._generate_cache_key(namespace, identifier)
        ttl = ttl or self.DEFAULT_TTL
        start_time = time.time()
        
        try:
            # Store in Redis (L2)
            redis_key = cache_key
            serialized_value = json.dumps(value, default=str)
            
            await self.redis_service.redis_client.setex(
                redis_key,
                ttl,
                serialized_value
            )
            
            # Store in memory cache (L1)
            await self._store_in_memory_cache(cache_key, value, ttl)
            
            duration_ms = (time.time() - start_time) * 1000
            logger.debug(
                f"Cache set: {namespace}:{identifier}",
                cache_key=cache_key,
                ttl=ttl,
                duration_ms=duration_ms,
                size_bytes=len(serialized_value)
            )
            
            return True
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                f"Cache set error: {namespace}:{identifier}",
                exception=e,
                cache_key=cache_key,
                duration_ms=duration_ms
            )
            return False
    
    async def _store_in_memory_cache(self, cache_key: str, value: Any, ttl: Optional[int]):
        """Store value in memory cache with eviction if needed."""
        # Check if eviction is needed
        if self._should_evict_from_memory():
            self._evict_from_memory_cache()
        
        # Calculate expiration
        expires_at = None
        if ttl:
            expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        
        # Create cache entry
        entry = CacheEntry(
            key=cache_key,
            value=value,
            created_at=datetime.utcnow(),
            expires_at=expires_at,
            access_count=1,
            last_accessed=datetime.utcnow(),
            size_bytes=self._calculate_size(value)
        )
        
        self.memory_cache[cache_key] = entry
        self.stats['cache_size'] = len(self.memory_cache)
    
    async def delete(self, namespace: str, identifier: str) -> bool:
        """
        Delete value from all cache layers.
        
        Args:
            namespace: Cache namespace
            identifier: Cache identifier
            
        Returns:
            True if successful, False otherwise
        """
        cache_key = self._generate_cache_key(namespace, identifier)
        
        try:
            # Remove from memory cache
            if cache_key in self.memory_cache:
                del self.memory_cache[cache_key]
                self.stats['cache_size'] = len(self.memory_cache)
            
            # Remove from Redis
            redis_key = cache_key
            await self.redis_service.redis_client.delete(redis_key)
            
            logger.debug(f"Cache delete: {namespace}:{identifier}", cache_key=cache_key)
            return True
            
        except Exception as e:
            logger.error(
                f"Cache delete error: {namespace}:{identifier}",
                exception=e,
                cache_key=cache_key
            )
            return False
    
    async def get_or_set(
        self,
        namespace: str,
        identifier: str,
        factory_func: Callable[[], Any],
        ttl: Optional[int] = None
    ) -> Any:
        """
        Get value from cache or set it using factory function.
        
        Args:
            namespace: Cache namespace
            identifier: Cache identifier
            factory_func: Function to generate value if not cached
            ttl: Time to live in seconds
            
        Returns:
            Cached or generated value
        """
        # Try to get from cache first
        value = await self.get(namespace, identifier)
        
        if value is not None:
            return value
        
        # Generate value using factory function
        try:
            if asyncio.iscoroutinefunction(factory_func):
                value = await factory_func()
            else:
                value = factory_func()
            
            # Cache the generated value
            if value is not None:
                await self.set(namespace, identifier, value, ttl)
            
            return value
            
        except Exception as e:
            logger.error(
                f"Factory function error: {namespace}:{identifier}",
                exception=e
            )
            return None
    
    async def warm_cache(self, namespace: str, identifiers: List[str], factory_func: Callable[[str], Any]):
        """
        Warm cache with multiple values using a factory function.
        
        Args:
            namespace: Cache namespace
            identifiers: List of identifiers to warm
            factory_func: Function to generate values
        """
        logger.info(f"Warming cache for {namespace} with {len(identifiers)} items")
        
        for identifier in identifiers:
            try:
                # Check if already cached
                cached_value = await self.get(namespace, identifier)
                if cached_value is not None:
                    continue
                
                # Generate and cache value
                if asyncio.iscoroutinefunction(factory_func):
                    value = await factory_func(identifier)
                else:
                    value = factory_func(identifier)
                
                if value is not None:
                    await self.set(namespace, identifier, value)
                
            except Exception as e:
                logger.error(
                    f"Cache warming error for {namespace}:{identifier}",
                    exception=e
                )
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        total_requests = self.stats['hits'] + self.stats['misses']
        hit_rate = (self.stats['hits'] / total_requests * 100) if total_requests > 0 else 0
        
        memory_cache_size_bytes = sum(entry.size_bytes for entry in self.memory_cache.values())
        
        return {
            'total_requests': total_requests,
            'hits': self.stats['hits'],
            'misses': self.stats['misses'],
            'hit_rate_percent': round(hit_rate, 2),
            'memory_hits': self.stats['memory_hits'],
            'redis_hits': self.stats['redis_hits'],
            'evictions': self.stats['evictions'],
            'memory_cache_size': len(self.memory_cache),
            'memory_cache_size_bytes': memory_cache_size_bytes,
            'max_memory_cache_size': self.max_memory_cache_size
        }
    
    async def clear_namespace(self, namespace: str) -> int:
        """
        Clear all cache entries for a specific namespace.
        
        Args:
            namespace: Namespace to clear
            
        Returns:
            Number of entries cleared
        """
        prefix = f"{self.CACHE_PREFIX}{namespace}:"
        cleared_count = 0
        
        try:
            # Clear from memory cache
            keys_to_remove = [key for key in self.memory_cache.keys() if key.startswith(prefix)]
            for key in keys_to_remove:
                del self.memory_cache[key]
                cleared_count += 1
            
            # Clear from Redis (scan for keys with prefix)
            async for key in self.redis_service.redis_client.scan_iter(match=f"{prefix}*"):
                await self.redis_service.redis_client.delete(key)
                cleared_count += 1
            
            self.stats['cache_size'] = len(self.memory_cache)
            
            logger.info(f"Cleared {cleared_count} entries from namespace: {namespace}")
            return cleared_count
            
        except Exception as e:
            logger.error(f"Error clearing namespace {namespace}", exception=e)
            return cleared_count