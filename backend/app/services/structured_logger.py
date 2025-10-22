"""
Structured logging service with request tracing and performance correlation.
"""
import logging
import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, Union
from contextvars import ContextVar
from dataclasses import dataclass, asdict
import traceback

# Context variables for request tracing
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar('user_id', default=None)


@dataclass
class LogContext:
    """Context information for structured logging."""
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    endpoint: Optional[str] = None
    method: Optional[str] = None
    session_id: Optional[str] = None
    correlation_id: Optional[str] = None


class StructuredLogger:
    """
    Structured logger with request tracing and performance correlation.
    
    Provides consistent logging format with contextual information
    for better debugging and monitoring.
    """
    
    def __init__(self, name: str):
        """
        Initialize structured logger.
        
        Args:
            name: Logger name (usually __name__)
        """
        self.logger = logging.getLogger(name)
        self.name = name
    
    def _get_base_context(self) -> Dict[str, Any]:
        """Get base context information for all log entries."""
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'logger': self.name,
            'request_id': request_id_var.get(),
            'user_id': user_id_var.get(),
        }
    
    def _format_message(
        self,
        level: str,
        message: str,
        extra_context: Optional[Dict[str, Any]] = None,
        exception: Optional[Exception] = None
    ) -> Dict[str, Any]:
        """
        Format log message with structured context.
        
        Args:
            level: Log level
            message: Log message
            extra_context: Additional context data
            exception: Exception object if logging an error
            
        Returns:
            Structured log entry dictionary
        """
        log_entry = self._get_base_context()
        log_entry.update({
            'level': level,
            'message': message,
        })
        
        if extra_context:
            log_entry['context'] = extra_context
        
        if exception:
            log_entry['exception'] = {
                'type': type(exception).__name__,
                'message': str(exception),
                'traceback': traceback.format_exc()
            }
        
        return log_entry
    
    def debug(self, message: str, **context):
        """Log debug message with context."""
        log_entry = self._format_message('DEBUG', message, context)
        self.logger.debug(json.dumps(log_entry))
    
    def info(self, message: str, **context):
        """Log info message with context."""
        log_entry = self._format_message('INFO', message, context)
        self.logger.info(json.dumps(log_entry))
    
    def warning(self, message: str, **context):
        """Log warning message with context."""
        log_entry = self._format_message('WARNING', message, context)
        self.logger.warning(json.dumps(log_entry))
    
    def error(self, message: str, exception: Optional[Exception] = None, **context):
        """Log error message with context and optional exception."""
        log_entry = self._format_message('ERROR', message, context, exception)
        self.logger.error(json.dumps(log_entry))
    
    def critical(self, message: str, exception: Optional[Exception] = None, **context):
        """Log critical message with context and optional exception."""
        log_entry = self._format_message('CRITICAL', message, context, exception)
        self.logger.critical(json.dumps(log_entry))
    
    # Performance-specific logging methods
    
    def log_api_call(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        response_time_ms: float,
        **context
    ):
        """Log API call with performance metrics."""
        self.info(
            f"API call completed: {method} {endpoint}",
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            response_time_ms=response_time_ms,
            **context
        )
    
    def log_slow_operation(
        self,
        operation: str,
        duration_ms: float,
        threshold_ms: float = 1000,
        **context
    ):
        """Log slow operation warning."""
        if duration_ms > threshold_ms:
            self.warning(
                f"Slow operation detected: {operation}",
                operation=operation,
                duration_ms=duration_ms,
                threshold_ms=threshold_ms,
                **context
            )
    
    def log_database_query(
        self,
        query_type: str,
        table: str,
        duration_ms: float,
        rows_affected: Optional[int] = None,
        **context
    ):
        """Log database query with performance metrics."""
        self.debug(
            f"Database query: {query_type} on {table}",
            query_type=query_type,
            table=table,
            duration_ms=duration_ms,
            rows_affected=rows_affected,
            **context
        )
    
    def log_redis_operation(
        self,
        operation: str,
        key: str,
        duration_ms: float,
        **context
    ):
        """Log Redis operation with performance metrics."""
        self.debug(
            f"Redis operation: {operation}",
            operation=operation,
            key=key,
            duration_ms=duration_ms,
            **context
        )
    
    def log_websocket_event(
        self,
        event: str,
        connection_id: str,
        data_size: Optional[int] = None,
        **context
    ):
        """Log WebSocket event."""
        self.debug(
            f"WebSocket event: {event}",
            event=event,
            connection_id=connection_id,
            data_size=data_size,
            **context
        )
    
    def log_gemini_api_call(
        self,
        request_type: str,
        response_time_ms: float,
        success: bool,
        tokens_used: Optional[int] = None,
        rate_limited: bool = False,
        **context
    ):
        """Log Gemini API call with metrics."""
        level = 'info' if success else 'warning'
        message = f"Gemini API call: {request_type}"
        
        if rate_limited:
            level = 'warning'
            message += " (rate limited)"
        
        getattr(self, level)(
            message,
            request_type=request_type,
            response_time_ms=response_time_ms,
            success=success,
            tokens_used=tokens_used,
            rate_limited=rate_limited,
            **context
        )
    
    def log_user_action(
        self,
        action: str,
        user_id: str,
        success: bool = True,
        **context
    ):
        """Log user action for audit trail."""
        self.info(
            f"User action: {action}",
            action=action,
            user_id=user_id,
            success=success,
            **context
        )
    
    def log_security_event(
        self,
        event_type: str,
        severity: str,
        details: Dict[str, Any],
        **context
    ):
        """Log security-related events."""
        log_method = getattr(self, severity.lower(), self.warning)
        log_method(
            f"Security event: {event_type}",
            event_type=event_type,
            severity=severity,
            details=details,
            **context
        )


class RequestTracer:
    """Context manager for request tracing."""
    
    def __init__(
        self,
        endpoint: Optional[str] = None,
        method: Optional[str] = None,
        user_id: Optional[str] = None,
        generate_request_id: bool = True
    ):
        """
        Initialize request tracer.
        
        Args:
            endpoint: API endpoint
            method: HTTP method
            user_id: User identifier
            generate_request_id: Whether to generate a new request ID
        """
        self.endpoint = endpoint
        self.method = method
        self.user_id = user_id
        self.request_id = str(uuid.uuid4()) if generate_request_id else None
        
        # Store previous context values
        self.prev_request_id = None
        self.prev_user_id = None
    
    def __enter__(self):
        """Enter request context."""
        # Store previous values
        self.prev_request_id = request_id_var.get()
        self.prev_user_id = user_id_var.get()
        
        # Set new context
        if self.request_id:
            request_id_var.set(self.request_id)
        if self.user_id:
            user_id_var.set(self.user_id)
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit request context."""
        # Restore previous values
        request_id_var.set(self.prev_request_id)
        user_id_var.set(self.prev_user_id)
    
    async def __aenter__(self):
        """Async enter request context."""
        return self.__enter__()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async exit request context."""
        return self.__exit__(exc_type, exc_val, exc_tb)


def get_structured_logger(name: str) -> StructuredLogger:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        StructuredLogger instance
    """
    return StructuredLogger(name)


def set_request_context(request_id: str, user_id: Optional[str] = None):
    """
    Set request context variables.
    
    Args:
        request_id: Request identifier
        user_id: Optional user identifier
    """
    request_id_var.set(request_id)
    if user_id:
        user_id_var.set(user_id)


def get_request_context() -> Dict[str, Optional[str]]:
    """
    Get current request context.
    
    Returns:
        Dictionary with request_id and user_id
    """
    return {
        'request_id': request_id_var.get(),
        'user_id': user_id_var.get()
    }


def clear_request_context():
    """Clear request context variables."""
    request_id_var.set(None)
    user_id_var.set(None)