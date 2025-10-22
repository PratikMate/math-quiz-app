"""
Security utilities for the Competitive Math Quiz application.
Handles API key management, rate limiting, and security best practices.
"""

import os
import secrets
import hashlib
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging

logger = logging.getLogger(__name__)

class APIKeyManager:
    """Manages API key security and rotation."""
    
    def __init__(self):
        self.current_key = os.getenv('GEMINI_API_KEY', '')
        self.key_created_at = datetime.utcnow()
        self.rotation_days = int(os.getenv('API_KEY_ROTATION_DAYS', '30'))
    
    def generate_secure_key(self, length: int = 64) -> str:
        """Generate a cryptographically secure random key."""
        return secrets.token_urlsafe(length)
    
    def hash_key(self, key: str) -> str:
        """Hash an API key for secure storage."""
        return hashlib.sha256(key.encode()).hexdigest()
    
    def is_key_expired(self) -> bool:
        """Check if the current API key needs rotation."""
        expiry_date = self.key_created_at + timedelta(days=self.rotation_days)
        return datetime.utcnow() > expiry_date
    
    def log_key_usage(self, endpoint: str, success: bool):
        """Log API key usage for monitoring."""
        status = "SUCCESS" if success else "FAILED"
        logger.info(f"API Key usage - Endpoint: {endpoint}, Status: {status}")
    
    def get_masked_key(self) -> str:
        """Get a masked version of the API key for logging."""
        if len(self.current_key) <= 8:
            return "*" * len(self.current_key)
        return self.current_key[:4] + "*" * (len(self.current_key) - 8) + self.current_key[-4:]

class RateLimiter:
    """Simple in-memory rate limiter for API endpoints."""
    
    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, list] = {}
    
    def is_allowed(self, identifier: str) -> bool:
        """Check if a request is allowed based on rate limits."""
        now = time.time()
        
        # Initialize or get existing request history
        if identifier not in self.requests:
            self.requests[identifier] = []
        
        request_times = self.requests[identifier]
        
        # Remove old requests outside the window
        cutoff_time = now - self.window_seconds
        request_times[:] = [req_time for req_time in request_times if req_time > cutoff_time]
        
        # Check if under limit
        if len(request_times) < self.max_requests:
            request_times.append(now)
            return True
        
        return False
    
    def get_reset_time(self, identifier: str) -> Optional[int]:
        """Get the time when rate limit resets for an identifier."""
        if identifier not in self.requests or not self.requests[identifier]:
            return None
        
        oldest_request = min(self.requests[identifier])
        return int(oldest_request + self.window_seconds)

class SecurityHeaders:
    """Security headers middleware for production."""
    
    @staticmethod
    def get_security_headers() -> Dict[str, str]:
        """Get security headers for HTTP responses."""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';",
        }

class InputValidator:
    """Input validation utilities."""
    
    @staticmethod
    def validate_username(username: str) -> bool:
        """Validate username format and content."""
        if not username or len(username) < 2 or len(username) > 50:
            return False
        
        # Allow alphanumeric, spaces, underscores, and hyphens
        allowed_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 _-')
        return all(c in allowed_chars for c in username)
    
    @staticmethod
    def validate_answer(answer: str) -> bool:
        """Validate answer format."""
        if not answer or len(answer) > 100:
            return False
        
        # Allow numbers, decimal points, negative signs, and basic math symbols
        allowed_chars = set('0123456789.-+*/() ')
        return all(c in allowed_chars for c in answer)
    
    @staticmethod
    def sanitize_input(input_str: str) -> str:
        """Sanitize user input to prevent injection attacks."""
        if not input_str:
            return ""
        
        # Remove potentially dangerous characters
        dangerous_chars = ['<', '>', '"', "'", '&', '\x00', '\n', '\r', '\t']
        sanitized = input_str
        
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, '')
        
        return sanitized.strip()

# Global instances
api_key_manager = APIKeyManager()
rate_limiter = RateLimiter(
    max_requests=int(os.getenv('RATE_LIMIT_PER_MINUTE', '60')),
    window_seconds=60
)

def get_client_ip(request: Request) -> str:
    """Get client IP address from request, handling proxies."""
    # Check for forwarded headers (common in production deployments)
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        # Take the first IP in the chain
        return forwarded_for.split(',')[0].strip()
    
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip
    
    # Fallback to direct client IP
    return request.client.host if request.client else "unknown"

async def check_rate_limit(request: Request):
    """Middleware to check rate limits."""
    client_ip = get_client_ip(request)
    
    if not rate_limiter.is_allowed(client_ip):
        reset_time = rate_limiter.get_reset_time(client_ip)
        logger.warning(f"Rate limit exceeded for IP: {client_ip}")
        
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "Retry-After": str(reset_time - int(time.time())) if reset_time else "60",
                "X-RateLimit-Limit": str(rate_limiter.max_requests),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_time) if reset_time else str(int(time.time()) + 60)
            }
        )

def log_security_event(event_type: str, details: Dict[str, Any], request: Request = None):
    """Log security-related events for monitoring."""
    client_ip = get_client_ip(request) if request else "unknown"
    
    log_data = {
        "event_type": event_type,
        "timestamp": datetime.utcnow().isoformat(),
        "client_ip": client_ip,
        "details": details
    }
    
    logger.warning(f"Security Event: {log_data}")

# Environment-specific security configurations
def get_production_security_config() -> Dict[str, Any]:
    """Get security configuration for production environment."""
    return {
        "require_https": True,
        "secure_cookies": True,
        "csrf_protection": True,
        "rate_limiting": True,
        "input_validation": True,
        "security_headers": True,
        "api_key_rotation": True,
    }

def get_development_security_config() -> Dict[str, Any]:
    """Get security configuration for development environment."""
    return {
        "require_https": False,
        "secure_cookies": False,
        "csrf_protection": False,
        "rate_limiting": False,
        "input_validation": True,
        "security_headers": False,
        "api_key_rotation": False,
    }