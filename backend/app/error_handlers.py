"""
Production-ready error handling for the Competitive Math Quiz application.
Provides structured error responses and logging.
"""

import logging
import traceback
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
import socketio

logger = logging.getLogger(__name__)

class ErrorResponse(BaseModel):
    """Structured error response model."""
    error_code: str
    message: str
    timestamp: str
    request_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

class ErrorCodes:
    """Standard error codes for the application."""
    
    # General errors
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    RATE_LIMITED = "RATE_LIMITED"
    
    # Quiz-specific errors
    QUIZ_NOT_ACTIVE = "QUIZ_NOT_ACTIVE"
    INVALID_ANSWER = "INVALID_ANSWER"
    SUBMISSION_TIMEOUT = "SUBMISSION_TIMEOUT"
    PROBLEM_NOT_FOUND = "PROBLEM_NOT_FOUND"
    USER_NOT_IN_QUIZ = "USER_NOT_IN_QUIZ"
    DUPLICATE_SUBMISSION = "DUPLICATE_SUBMISSION"
    
    # Service errors
    DATABASE_ERROR = "DATABASE_ERROR"
    REDIS_ERROR = "REDIS_ERROR"
    AI_SERVICE_ERROR = "AI_SERVICE_ERROR"
    WEBSOCKET_ERROR = "WEBSOCKET_ERROR"
    
    # Network errors
    CONNECTION_LOST = "CONNECTION_LOST"
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"

class QuizException(Exception):
    """Base exception class for quiz-specific errors."""
    
    def __init__(
        self,
        message: str,
        error_code: str = ErrorCodes.INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = 500
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.status_code = status_code
        super().__init__(message)

class ValidationException(QuizException):
    """Exception for validation errors."""
    
    def __init__(self, message: str, field: str = None, value: Any = None):
        details = {}
        if field:
            details["field"] = field
        if value is not None:
            details["invalid_value"] = str(value)
        
        super().__init__(
            message=message,
            error_code=ErrorCodes.VALIDATION_ERROR,
            details=details,
            status_code=400
        )

class ServiceException(QuizException):
    """Exception for service-level errors."""
    
    def __init__(self, service: str, message: str, original_error: Exception = None):
        details = {"service": service}
        if original_error:
            details["original_error"] = str(original_error)
        
        super().__init__(
            message=f"{service} error: {message}",
            error_code=f"{service.upper()}_ERROR",
            details=details,
            status_code=503
        )

def create_error_response(
    error_code: str,
    message: str,
    request_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> ErrorResponse:
    """Create a standardized error response."""
    return ErrorResponse(
        error_code=error_code,
        message=message,
        timestamp=datetime.utcnow().isoformat(),
        request_id=request_id,
        details=details
    )

async def handle_quiz_exception(request: Request, exc: QuizException) -> JSONResponse:
    """Handle quiz-specific exceptions."""
    request_id = getattr(request.state, 'request_id', None)
    
    # Log the error
    logger.error(
        f"Quiz exception: {exc.error_code} - {exc.message}",
        extra={
            "error_code": exc.error_code,
            "request_id": request_id,
            "details": exc.details,
            "path": request.url.path,
            "method": request.method
        }
    )
    
    error_response = create_error_response(
        error_code=exc.error_code,
        message=exc.message,
        request_id=request_id,
        details=exc.details
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.dict()
    )

async def handle_validation_error(request: Request, exc: ValidationError) -> JSONResponse:
    """Handle Pydantic validation errors."""
    request_id = getattr(request.state, 'request_id', None)
    
    # Extract validation details
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })
    
    logger.warning(
        f"Validation error: {len(errors)} field(s) failed validation",
        extra={
            "request_id": request_id,
            "validation_errors": errors,
            "path": request.url.path,
            "method": request.method
        }
    )
    
    error_response = create_error_response(
        error_code=ErrorCodes.VALIDATION_ERROR,
        message="Validation failed",
        request_id=request_id,
        details={"validation_errors": errors}
    )
    
    return JSONResponse(
        status_code=422,
        content=error_response.dict()
    )

async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle FastAPI HTTP exceptions."""
    request_id = getattr(request.state, 'request_id', None)
    
    # Map HTTP status codes to error codes
    status_to_error_code = {
        400: ErrorCodes.VALIDATION_ERROR,
        401: ErrorCodes.UNAUTHORIZED,
        404: ErrorCodes.NOT_FOUND,
        429: ErrorCodes.RATE_LIMITED,
        500: ErrorCodes.INTERNAL_SERVER_ERROR,
    }
    
    error_code = status_to_error_code.get(exc.status_code, ErrorCodes.INTERNAL_SERVER_ERROR)
    
    logger.warning(
        f"HTTP exception: {exc.status_code} - {exc.detail}",
        extra={
            "status_code": exc.status_code,
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method
        }
    )
    
    error_response = create_error_response(
        error_code=error_code,
        message=str(exc.detail),
        request_id=request_id
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.dict()
    )

async def handle_general_exception(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    request_id = getattr(request.state, 'request_id', None)
    
    # Log the full traceback for debugging
    logger.error(
        f"Unhandled exception: {type(exc).__name__}: {str(exc)}",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "traceback": traceback.format_exc()
        },
        exc_info=True
    )
    
    # Don't expose internal error details in production
    from config import settings
    if settings.DEBUG:
        message = f"{type(exc).__name__}: {str(exc)}"
        details = {"traceback": traceback.format_exc()}
    else:
        message = "An unexpected error occurred"
        details = None
    
    error_response = create_error_response(
        error_code=ErrorCodes.INTERNAL_SERVER_ERROR,
        message=message,
        request_id=request_id,
        details=details
    )
    
    return JSONResponse(
        status_code=500,
        content=error_response.dict()
    )

# WebSocket error handling
async def handle_websocket_error(sio: socketio.AsyncServer, sid: str, error: Exception, event_name: str = None):
    """Handle WebSocket errors and send error messages to clients."""
    
    # Log the error
    logger.error(
        f"WebSocket error in event '{event_name}': {type(error).__name__}: {str(error)}",
        extra={
            "sid": sid,
            "event": event_name,
            "error_type": type(error).__name__
        },
        exc_info=True
    )
    
    # Determine error code and message
    if isinstance(error, QuizException):
        error_code = error.error_code
        message = error.message
    elif isinstance(error, ValidationError):
        error_code = ErrorCodes.VALIDATION_ERROR
        message = "Invalid data format"
    else:
        error_code = ErrorCodes.WEBSOCKET_ERROR
        message = "WebSocket operation failed"
    
    # Send error to client
    try:
        await sio.emit('error', {
            'error_code': error_code,
            'message': message,
            'timestamp': datetime.utcnow().isoformat(),
            'event': event_name
        }, room=sid)
    except Exception as emit_error:
        logger.error(f"Failed to emit error to client {sid}: {emit_error}")

# Utility functions for common error scenarios
def raise_not_found(resource: str, identifier: str = None):
    """Raise a not found exception."""
    message = f"{resource} not found"
    if identifier:
        message += f": {identifier}"
    
    raise QuizException(
        message=message,
        error_code=ErrorCodes.NOT_FOUND,
        details={"resource": resource, "identifier": identifier},
        status_code=404
    )

def raise_validation_error(message: str, field: str = None, value: Any = None):
    """Raise a validation exception."""
    raise ValidationException(message=message, field=field, value=value)

def raise_service_error(service: str, message: str, original_error: Exception = None):
    """Raise a service exception."""
    raise ServiceException(service=service, message=message, original_error=original_error)

def raise_quiz_error(message: str, error_code: str = ErrorCodes.QUIZ_NOT_ACTIVE):
    """Raise a quiz-specific exception."""
    raise QuizException(
        message=message,
        error_code=error_code,
        status_code=400
    )