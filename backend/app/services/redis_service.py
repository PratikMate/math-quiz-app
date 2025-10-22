"""
Redis service for managing connections and basic operations.
"""
import os
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set, Union
from datetime import datetime, timedelta
import redis.asyncio as redis
from redis.asyncio import ConnectionPool

from .structured_logger import get_structured_logger
from .performance_monitor import performance_monitor


logger = get_structured_logger(__name__)


class RedisService:
    """
    Redis service for managing connections and basic operations.
    
    Provides connection pooling, current problem state storage,
    and active users tracking for the competitive math quiz system.
    """
    
    def __init__(self, redis_url: Optional[str] = None):
        """
        Initialize Redis service with connection pooling.
        
        Args:
            redis_url: Redis connection URL. If None, uses REDIS_URL env var.
        """
        self.redis_url = redis_url or os.getenv('REDIS_URL', 'redis://localhost:6379')
        self.pool: Optional[ConnectionPool] = None
        self.redis_client: Optional[redis.Redis] = None
        
        # Key prefixes for different data types
        self.CURRENT_PROBLEM_KEY = "quiz:current_problem"
        self.ACTIVE_USERS_KEY = "quiz:active_users"
        self.USER_SESSIONS_KEY = "quiz:user_sessions"
        self.PROBLEM_SUBMISSIONS_PREFIX = "quiz:submissions"
        self.SOLVED_PROBLEMS_KEY = "quiz:solved_problems"
        self.USER_SUBMISSIONS_PREFIX = "quiz:user_submissions"
        
        # Default expiration times
        self.DEFAULT_EXPIRY = 3600  # 1 hour
        self.SESSION_EXPIRY = 7200  # 2 hours
        self.PROBLEM_EXPIRY = 1800  # 30 minutes
        
        # Performance optimization settings
        self.batch_operations = []
        self.batch_size_limit = 100
        self.batch_timeout = 0.1  # 100ms
    
    async def connect(self) -> None:
        """
        Establish Redis connection with connection pooling.
        
        Raises:
            ConnectionError: If unable to connect to Redis
        """
        try:
            # Simple Redis connection
            self.redis_client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            
            # Test connection
            await self.redis_client.ping()
            logger.info("Successfully connected to Redis")
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            # Don't raise in development to allow graceful degradation
            if os.getenv('ENVIRONMENT') == 'production':
                raise ConnectionError(f"Redis connection failed: {e}")
            else:
                logger.warning("Redis connection failed, continuing without Redis in development mode")
    
    async def disconnect(self) -> None:
        """Close Redis connection and cleanup resources."""
        try:
            if self.redis_client:
                await self.redis_client.close()
            if self.pool:
                await self.pool.disconnect()
            logger.info("Disconnected from Redis")
        except Exception as e:
            logger.error(f"Error disconnecting from Redis: {e}")
    
    async def is_connected(self) -> bool:
        """
        Check if Redis connection is active.
        
        Returns:
            True if connected, False otherwise
        """
        try:
            if not self.redis_client:
                return False
            await self.redis_client.ping()
            return True
        except Exception:
            return False
    
    # Current Problem State Management
    
    async def set_current_problem(self, problem_data: Dict[str, Any]) -> bool:
        """
        Store current problem state in Redis.
        
        Args:
            problem_data: Dictionary containing problem information
            
        Returns:
            True if successful, False otherwise
        """
        start_time = time.time()
        try:
            # Add timestamp
            problem_data['stored_at'] = datetime.utcnow().isoformat()
            
            # Store as JSON with expiration
            await self.redis_client.setex(
                self.CURRENT_PROBLEM_KEY,
                self.PROBLEM_EXPIRY,
                json.dumps(problem_data, default=str)
            )
            
            duration_ms = (time.time() - start_time) * 1000
            logger.log_redis_operation(
                operation="setex",
                key=self.CURRENT_PROBLEM_KEY,
                duration_ms=duration_ms,
                problem_id=problem_data.get('id', 'unknown')
            )
            
            logger.info(f"Stored current problem: {problem_data.get('id', 'unknown')}")
            return True
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"Failed to store current problem: {e}", exception=e, duration_ms=duration_ms)
            return False
    
    async def get_current_problem(self) -> Optional[Dict[str, Any]]:
        """
        Retrieve current problem state from Redis.
        
        Returns:
            Problem data dictionary or None if not found
        """
        start_time = time.time()
        try:
            data = await self.redis_client.get(self.CURRENT_PROBLEM_KEY)
            duration_ms = (time.time() - start_time) * 1000
            
            logger.log_redis_operation(
                operation="get",
                key=self.CURRENT_PROBLEM_KEY,
                duration_ms=duration_ms,
                found=data is not None
            )
            
            if data:
                return json.loads(data)
            return None
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"Failed to retrieve current problem: {e}", exception=e, duration_ms=duration_ms)
            return None
    
    async def clear_current_problem(self) -> bool:
        """
        Clear current problem state from Redis.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            await self.redis_client.delete(self.CURRENT_PROBLEM_KEY)
            logger.info("Cleared current problem state")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear current problem: {e}")
            return False
    
    # Active Users Tracking
    
    async def add_active_user(self, user_id: str, user_data: Dict[str, Any]) -> bool:
        """
        Add user to active users set and store session data.
        
        Args:
            user_id: User identifier
            user_data: User session information
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Add to active users set
            await self.redis_client.sadd(self.ACTIVE_USERS_KEY, user_id)
            
            # Store user session data
            user_key = f"{self.USER_SESSIONS_KEY}:{user_id}"
            user_data['last_active'] = datetime.utcnow().isoformat()
            
            await self.redis_client.setex(
                user_key,
                self.SESSION_EXPIRY,
                json.dumps(user_data, default=str)
            )
            
            logger.info(f"Added active user: {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add active user {user_id}: {e}")
            return False
    
    async def remove_active_user(self, user_id: str) -> bool:
        """
        Remove user from active users set and cleanup session data.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Remove from active users set
            await self.redis_client.srem(self.ACTIVE_USERS_KEY, user_id)
            
            # Remove user session data
            user_key = f"{self.USER_SESSIONS_KEY}:{user_id}"
            await self.redis_client.delete(user_key)
            
            logger.info(f"Removed active user: {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove active user {user_id}: {e}")
            return False
    
    async def get_active_users(self) -> Set[str]:
        """
        Get set of active user IDs.
        
        Returns:
            Set of active user IDs
        """
        try:
            users = await self.redis_client.smembers(self.ACTIVE_USERS_KEY)
            return {user.decode() if isinstance(user, bytes) else user for user in users}
            
        except Exception as e:
            logger.error(f"Failed to get active users: {e}")
            return set()
    
    async def get_active_users_count(self) -> int:
        """
        Get count of active users.
        
        Returns:
            Number of active users
        """
        try:
            return await self.redis_client.scard(self.ACTIVE_USERS_KEY)
            
        except Exception as e:
            logger.error(f"Failed to get active users count: {e}")
            return 0
    
    async def get_user_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user session data.
        
        Args:
            user_id: User identifier
            
        Returns:
            User session data or None if not found
        """
        try:
            user_key = f"{self.USER_SESSIONS_KEY}:{user_id}"
            data = await self.redis_client.get(user_key)
            if data:
                return json.loads(data)
            return None
            
        except Exception as e:
            logger.error(f"Failed to get user session {user_id}: {e}")
            return None
    
    async def update_user_session(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update user session data.
        
        Args:
            user_id: User identifier
            updates: Dictionary of updates to apply
            
        Returns:
            True if successful, False otherwise
        """
        try:
            user_key = f"{self.USER_SESSIONS_KEY}:{user_id}"
            
            # Get existing data
            existing_data = await self.get_user_session(user_id)
            if existing_data is None:
                existing_data = {}
            
            # Apply updates
            existing_data.update(updates)
            existing_data['last_active'] = datetime.utcnow().isoformat()
            
            # Store updated data
            await self.redis_client.setex(
                user_key,
                self.SESSION_EXPIRY,
                json.dumps(existing_data, default=str)
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update user session {user_id}: {e}")
            return False
    
    async def get_all_user_sessions(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all active user sessions.
        
        Returns:
            Dictionary mapping user_id to session data
        """
        try:
            active_users = await self.get_active_users()
            sessions = {}
            
            for user_id in active_users:
                session_data = await self.get_user_session(user_id)
                if session_data:
                    sessions[user_id] = session_data
            
            return sessions
            
        except Exception as e:
            logger.error(f"Failed to get all user sessions: {e}")
            return {}
    
    # Utility Methods
    
    async def cleanup_expired_users(self) -> int:
        """
        Remove expired users from active set.
        
        Returns:
            Number of users cleaned up
        """
        try:
            active_users = await self.get_active_users()
            cleaned_count = 0
            
            for user_id in active_users:
                session_data = await self.get_user_session(user_id)
                if session_data is None:
                    # Session expired, remove from active set
                    await self.redis_client.srem(self.ACTIVE_USERS_KEY, user_id)
                    cleaned_count += 1
            
            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} expired users")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired users: {e}")
            return 0
    
    async def get_redis_info(self) -> Dict[str, Any]:
        """
        Get Redis server information for monitoring.
        
        Returns:
            Dictionary with Redis server info
        """
        try:
            info = await self.redis_client.info()
            return {
                'connected_clients': info.get('connected_clients', 0),
                'used_memory_human': info.get('used_memory_human', 'unknown'),
                'redis_version': info.get('redis_version', 'unknown'),
                'uptime_in_seconds': info.get('uptime_in_seconds', 0)
            }
            
        except Exception as e:
            logger.error(f"Failed to get Redis info: {e}")
            return {}
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on Redis connection.
        
        Returns:
            Health check results
        """
        try:
            start_time = datetime.utcnow()
            await self.redis_client.ping()
            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            active_users_count = await self.get_active_users_count()
            current_problem = await self.get_current_problem()
            
            return {
                'status': 'healthy',
                'response_time_ms': round(response_time, 2),
                'active_users': active_users_count,
                'has_current_problem': current_problem is not None,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    # Batch Operations for Performance Optimization
    
    async def batch_execute(self, operations: List[Dict[str, Any]]) -> List[Any]:
        """
        Execute multiple Redis operations in a single pipeline for better performance.
        
        Args:
            operations: List of operation dictionaries with 'command', 'args', 'kwargs'
            
        Returns:
            List of operation results
        """
        if not operations:
            return []
        
        start_time = time.time()
        try:
            pipeline = self.redis_client.pipeline()
            
            # Add all operations to pipeline
            for op in operations:
                command = op['command']
                args = op.get('args', [])
                kwargs = op.get('kwargs', {})
                
                # Get the method from pipeline and call it
                method = getattr(pipeline, command)
                method(*args, **kwargs)
            
            # Execute all operations
            results = await pipeline.execute()
            
            duration_ms = (time.time() - start_time) * 1000
            logger.log_redis_operation(
                operation="batch_execute",
                key=f"batch_{len(operations)}_ops",
                duration_ms=duration_ms,
                operations_count=len(operations)
            )
            
            return results
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                f"Batch operation failed: {e}",
                exception=e,
                duration_ms=duration_ms,
                operations_count=len(operations)
            )
            raise
    
    async def batch_get_user_sessions(self, user_ids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Get multiple user sessions in a single batch operation.
        
        Args:
            user_ids: List of user IDs to fetch
            
        Returns:
            Dictionary mapping user_id to session data
        """
        if not user_ids:
            return {}
        
        start_time = time.time()
        try:
            # Prepare batch operations
            operations = []
            for user_id in user_ids:
                user_key = f"{self.USER_SESSIONS_KEY}:{user_id}"
                operations.append({
                    'command': 'get',
                    'args': [user_key]
                })
            
            # Execute batch
            results = await self.batch_execute(operations)
            
            # Parse results
            sessions = {}
            for i, user_id in enumerate(user_ids):
                data = results[i] if i < len(results) else None
                if data:
                    try:
                        sessions[user_id] = json.loads(data)
                    except json.JSONDecodeError:
                        sessions[user_id] = None
                else:
                    sessions[user_id] = None
            
            duration_ms = (time.time() - start_time) * 1000
            logger.log_redis_operation(
                operation="batch_get_user_sessions",
                key=f"batch_{len(user_ids)}_sessions",
                duration_ms=duration_ms,
                user_count=len(user_ids)
            )
            
            return sessions
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                f"Batch get user sessions failed: {e}",
                exception=e,
                duration_ms=duration_ms,
                user_count=len(user_ids)
            )
            return {user_id: None for user_id in user_ids}
    
    async def batch_update_user_sessions(self, updates: Dict[str, Dict[str, Any]]) -> bool:
        """
        Update multiple user sessions in a single batch operation.
        
        Args:
            updates: Dictionary mapping user_id to update data
            
        Returns:
            True if successful, False otherwise
        """
        if not updates:
            return True
        
        start_time = time.time()
        try:
            # Get existing sessions first
            user_ids = list(updates.keys())
            existing_sessions = await self.batch_get_user_sessions(user_ids)
            
            # Prepare batch update operations
            operations = []
            for user_id, update_data in updates.items():
                user_key = f"{self.USER_SESSIONS_KEY}:{user_id}"
                
                # Merge with existing data
                existing_data = existing_sessions.get(user_id, {}) or {}
                existing_data.update(update_data)
                existing_data['last_active'] = datetime.utcnow().isoformat()
                
                operations.append({
                    'command': 'setex',
                    'args': [user_key, self.SESSION_EXPIRY, json.dumps(existing_data, default=str)]
                })
            
            # Execute batch update
            await self.batch_execute(operations)
            
            duration_ms = (time.time() - start_time) * 1000
            logger.log_redis_operation(
                operation="batch_update_user_sessions",
                key=f"batch_{len(updates)}_updates",
                duration_ms=duration_ms,
                update_count=len(updates)
            )
            
            return True
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                f"Batch update user sessions failed: {e}",
                exception=e,
                duration_ms=duration_ms,
                update_count=len(updates)
            )
            return False
    
    async def get_memory_usage(self) -> Dict[str, Any]:
        """
        Get Redis memory usage statistics for monitoring.
        
        Returns:
            Dictionary with memory usage information
        """
        try:
            info = await self.redis_client.info('memory')
            
            return {
                'used_memory': info.get('used_memory', 0),
                'used_memory_human': info.get('used_memory_human', '0B'),
                'used_memory_rss': info.get('used_memory_rss', 0),
                'used_memory_peak': info.get('used_memory_peak', 0),
                'used_memory_peak_human': info.get('used_memory_peak_human', '0B'),
                'memory_fragmentation_ratio': info.get('mem_fragmentation_ratio', 0),
                'maxmemory': info.get('maxmemory', 0),
                'maxmemory_human': info.get('maxmemory_human', 'unlimited')
            }
            
        except Exception as e:
            logger.error(f"Failed to get Redis memory usage: {e}", exception=e)
            return {}