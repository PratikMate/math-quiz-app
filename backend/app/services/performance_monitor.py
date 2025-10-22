"""
Performance monitoring service for tracking API calls, response times, and system metrics.
"""
import asyncio
import logging
import time
import psutil
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from collections import defaultdict, deque
import json
import traceback
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


@dataclass
class APICallMetric:
    """Represents a single API call metric."""
    endpoint: str
    method: str
    status_code: int
    response_time_ms: float
    timestamp: datetime
    user_id: Optional[str] = None
    error: Optional[str] = None
    memory_usage_mb: Optional[float] = None


@dataclass
class SystemMetrics:
    """System-level performance metrics."""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    active_connections: int
    redis_memory_mb: Optional[float] = None
    database_connections: Optional[int] = None


@dataclass
class GeminiAPIMetrics:
    """Gemini API specific metrics."""
    timestamp: datetime
    request_type: str
    response_time_ms: float
    success: bool
    tokens_used: Optional[int] = None
    rate_limited: bool = False
    error: Optional[str] = None


class PerformanceMonitor:
    """
    Centralized performance monitoring service.
    
    Tracks API response times, system metrics, WebSocket connections,
    and provides structured logging with request tracing.
    """
    
    def __init__(self, max_metrics_history: int = 1000):
        """
        Initialize performance monitor.
        
        Args:
            max_metrics_history: Maximum number of metrics to keep in memory
        """
        self.max_metrics_history = max_metrics_history
        
        # Metrics storage
        self.api_metrics: deque = deque(maxlen=max_metrics_history)
        self.system_metrics: deque = deque(maxlen=max_metrics_history)
        self.gemini_metrics: deque = deque(maxlen=max_metrics_history)
        self.websocket_metrics: Dict[str, Any] = defaultdict(dict)
        
        # Request tracking
        self.active_requests: Dict[str, Dict[str, Any]] = {}
        self.request_counter = 0
        
        # Performance thresholds
        self.slow_request_threshold_ms = 1000
        self.high_memory_threshold_percent = 80
        self.high_cpu_threshold_percent = 80
        
        # Monitoring state
        self.monitoring_active = False
        self.system_monitor_task: Optional[asyncio.Task] = None
        
    async def start_monitoring(self):
        """Start background system monitoring."""
        if self.monitoring_active:
            return
            
        self.monitoring_active = True
        self.system_monitor_task = asyncio.create_task(self._system_monitor_loop())
        logger.info("Performance monitoring started")
    
    async def stop_monitoring(self):
        """Stop background system monitoring."""
        self.monitoring_active = False
        if self.system_monitor_task:
            self.system_monitor_task.cancel()
            try:
                await self.system_monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Performance monitoring stopped")
    
    @asynccontextmanager
    async def track_request(self, endpoint: str, method: str, user_id: Optional[str] = None):
        """
        Context manager for tracking API request performance.
        
        Args:
            endpoint: API endpoint being called
            method: HTTP method
            user_id: Optional user identifier
            
        Usage:
            async with monitor.track_request("/api/submit", "POST", user_id) as tracker:
                # Your API logic here
                tracker.set_status(200)
        """
        request_id = f"req_{self.request_counter}"
        self.request_counter += 1
        
        start_time = time.time()
        start_memory = self._get_memory_usage()
        
        # Track active request
        self.active_requests[request_id] = {
            'endpoint': endpoint,
            'method': method,
            'user_id': user_id,
            'start_time': start_time,
            'start_memory': start_memory
        }
        
        class RequestTracker:
            def __init__(self, monitor_instance):
                self.monitor = monitor_instance
                self.status_code = 200
                self.error = None
                
            def set_status(self, status_code: int):
                self.status_code = status_code
                
            def set_error(self, error: str):
                self.error = error
                self.status_code = 500
        
        tracker = RequestTracker(self)
        
        try:
            yield tracker
        except Exception as e:
            tracker.set_error(str(e))
            raise
        finally:
            # Calculate metrics
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            end_memory = self._get_memory_usage()
            
            # Create metric
            metric = APICallMetric(
                endpoint=endpoint,
                method=method,
                status_code=tracker.status_code,
                response_time_ms=response_time_ms,
                timestamp=datetime.utcnow(),
                user_id=user_id,
                error=tracker.error,
                memory_usage_mb=end_memory - start_memory if end_memory and start_memory else None
            )
            
            # Store metric
            self.api_metrics.append(metric)
            
            # Log slow requests
            if response_time_ms > self.slow_request_threshold_ms:
                logger.warning(
                    f"Slow request detected: {method} {endpoint} took {response_time_ms:.2f}ms "
                    f"(user: {user_id}, status: {tracker.status_code})"
                )
            
            # Remove from active requests
            self.active_requests.pop(request_id, None)
    
    def track_websocket_connection(self, connection_id: str, event: str, data: Optional[Dict] = None):
        """
        Track WebSocket connection events.
        
        Args:
            connection_id: WebSocket connection identifier
            event: Event type (connect, disconnect, message, etc.)
            data: Optional event data
        """
        timestamp = datetime.utcnow()
        
        if connection_id not in self.websocket_metrics:
            self.websocket_metrics[connection_id] = {
                'connected_at': timestamp,
                'events': deque(maxlen=100),
                'message_count': 0,
                'last_activity': timestamp
            }
        
        connection_metrics = self.websocket_metrics[connection_id]
        connection_metrics['events'].append({
            'event': event,
            'timestamp': timestamp,
            'data': data
        })
        connection_metrics['last_activity'] = timestamp
        
        if event in ['message', 'submit_answer', 'join_quiz']:
            connection_metrics['message_count'] += 1
    
    def track_gemini_api_call(
        self,
        request_type: str,
        response_time_ms: float,
        success: bool,
        tokens_used: Optional[int] = None,
        rate_limited: bool = False,
        error: Optional[str] = None
    ):
        """
        Track Gemini API call metrics.
        
        Args:
            request_type: Type of request (generate_problem, etc.)
            response_time_ms: Response time in milliseconds
            success: Whether the request was successful
            tokens_used: Number of tokens used (if available)
            rate_limited: Whether the request was rate limited
            error: Error message if any
        """
        metric = GeminiAPIMetrics(
            timestamp=datetime.utcnow(),
            request_type=request_type,
            response_time_ms=response_time_ms,
            success=success,
            tokens_used=tokens_used,
            rate_limited=rate_limited,
            error=error
        )
        
        self.gemini_metrics.append(metric)
        
        # Log rate limiting
        if rate_limited:
            logger.warning(f"Gemini API rate limited for {request_type}")
        
        # Log slow API calls
        if response_time_ms > 5000:  # 5 seconds
            logger.warning(f"Slow Gemini API call: {request_type} took {response_time_ms:.2f}ms")
    
    async def _system_monitor_loop(self):
        """Background loop for collecting system metrics."""
        while self.monitoring_active:
            try:
                # Collect system metrics
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                
                metric = SystemMetrics(
                    timestamp=datetime.utcnow(),
                    cpu_percent=cpu_percent,
                    memory_percent=memory.percent,
                    memory_used_mb=memory.used / 1024 / 1024,
                    active_connections=len(self.websocket_metrics)
                )
                
                self.system_metrics.append(metric)
                
                # Log high resource usage
                if cpu_percent > self.high_cpu_threshold_percent:
                    logger.warning(f"High CPU usage detected: {cpu_percent:.1f}%")
                
                if memory.percent > self.high_memory_threshold_percent:
                    logger.warning(f"High memory usage detected: {memory.percent:.1f}%")
                
                # Wait before next collection
                await asyncio.sleep(30)  # Collect every 30 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in system monitoring: {e}")
                await asyncio.sleep(30)
    
    def _get_memory_usage(self) -> Optional[float]:
        """Get current memory usage in MB."""
        try:
            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024
        except Exception:
            return None
    
    def get_api_performance_summary(self, minutes: int = 60) -> Dict[str, Any]:
        """
        Get API performance summary for the last N minutes.
        
        Args:
            minutes: Time window in minutes
            
        Returns:
            Performance summary dictionary
        """
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        recent_metrics = [m for m in self.api_metrics if m.timestamp > cutoff_time]
        
        if not recent_metrics:
            return {
                'total_requests': 0,
                'avg_response_time_ms': 0,
                'slow_requests': 0,
                'error_rate': 0,
                'endpoints': {}
            }
        
        # Calculate summary statistics
        total_requests = len(recent_metrics)
        avg_response_time = sum(m.response_time_ms for m in recent_metrics) / total_requests
        slow_requests = sum(1 for m in recent_metrics if m.response_time_ms > self.slow_request_threshold_ms)
        error_requests = sum(1 for m in recent_metrics if m.status_code >= 400)
        
        # Group by endpoint
        endpoint_stats = defaultdict(lambda: {'count': 0, 'avg_time': 0, 'errors': 0})
        for metric in recent_metrics:
            key = f"{metric.method} {metric.endpoint}"
            endpoint_stats[key]['count'] += 1
            endpoint_stats[key]['avg_time'] += metric.response_time_ms
            if metric.status_code >= 400:
                endpoint_stats[key]['errors'] += 1
        
        # Calculate averages
        for stats in endpoint_stats.values():
            if stats['count'] > 0:
                stats['avg_time'] /= stats['count']
        
        return {
            'total_requests': total_requests,
            'avg_response_time_ms': round(avg_response_time, 2),
            'slow_requests': slow_requests,
            'error_rate': round((error_requests / total_requests) * 100, 2),
            'endpoints': dict(endpoint_stats),
            'time_window_minutes': minutes
        }
    
    def get_system_performance_summary(self) -> Dict[str, Any]:
        """Get current system performance summary."""
        if not self.system_metrics:
            return {'status': 'no_data'}
        
        latest_metric = self.system_metrics[-1]
        
        # Calculate averages over last 10 minutes
        ten_minutes_ago = datetime.utcnow() - timedelta(minutes=10)
        recent_metrics = [m for m in self.system_metrics if m.timestamp > ten_minutes_ago]
        
        if recent_metrics:
            avg_cpu = sum(m.cpu_percent for m in recent_metrics) / len(recent_metrics)
            avg_memory = sum(m.memory_percent for m in recent_metrics) / len(recent_metrics)
        else:
            avg_cpu = latest_metric.cpu_percent
            avg_memory = latest_metric.memory_percent
        
        return {
            'current_cpu_percent': latest_metric.cpu_percent,
            'current_memory_percent': latest_metric.memory_percent,
            'current_memory_used_mb': latest_metric.memory_used_mb,
            'avg_cpu_10min': round(avg_cpu, 2),
            'avg_memory_10min': round(avg_memory, 2),
            'active_websocket_connections': latest_metric.active_connections,
            'active_api_requests': len(self.active_requests),
            'timestamp': latest_metric.timestamp.isoformat()
        }
    
    def get_gemini_api_summary(self, minutes: int = 60) -> Dict[str, Any]:
        """
        Get Gemini API performance summary.
        
        Args:
            minutes: Time window in minutes
            
        Returns:
            Gemini API summary dictionary
        """
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        recent_metrics = [m for m in self.gemini_metrics if m.timestamp > cutoff_time]
        
        if not recent_metrics:
            return {
                'total_requests': 0,
                'success_rate': 0,
                'avg_response_time_ms': 0,
                'rate_limited_requests': 0
            }
        
        total_requests = len(recent_metrics)
        successful_requests = sum(1 for m in recent_metrics if m.success)
        rate_limited_requests = sum(1 for m in recent_metrics if m.rate_limited)
        avg_response_time = sum(m.response_time_ms for m in recent_metrics) / total_requests
        
        return {
            'total_requests': total_requests,
            'success_rate': round((successful_requests / total_requests) * 100, 2),
            'avg_response_time_ms': round(avg_response_time, 2),
            'rate_limited_requests': rate_limited_requests,
            'rate_limit_percentage': round((rate_limited_requests / total_requests) * 100, 2),
            'time_window_minutes': minutes
        }
    
    def get_websocket_summary(self) -> Dict[str, Any]:
        """Get WebSocket connections summary."""
        active_connections = 0
        total_messages = 0
        recent_activity = 0
        
        five_minutes_ago = datetime.utcnow() - timedelta(minutes=5)
        
        for connection_id, metrics in self.websocket_metrics.items():
            # Check if connection is still active (activity in last 5 minutes)
            if metrics['last_activity'] > five_minutes_ago:
                active_connections += 1
                recent_activity += 1
            
            total_messages += metrics['message_count']
        
        return {
            'total_connections': len(self.websocket_metrics),
            'active_connections': active_connections,
            'recent_activity_5min': recent_activity,
            'total_messages_processed': total_messages
        }
    
    def get_comprehensive_report(self) -> Dict[str, Any]:
        """Get comprehensive performance report."""
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'api_performance': self.get_api_performance_summary(),
            'system_performance': self.get_system_performance_summary(),
            'gemini_api': self.get_gemini_api_summary(),
            'websocket_connections': self.get_websocket_summary(),
            'monitoring_status': {
                'active': self.monitoring_active,
                'metrics_in_memory': {
                    'api_calls': len(self.api_metrics),
                    'system_metrics': len(self.system_metrics),
                    'gemini_calls': len(self.gemini_metrics)
                }
            }
        }


# Global performance monitor instance
performance_monitor = PerformanceMonitor()