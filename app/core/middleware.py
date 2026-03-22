"""
Security and Request Middlewares
"""

import logging
import time
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Security headers middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'none'"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response

# Payload size limiting middleware
class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_upload_size: int = 1048576): # Default 1MB
        super().__init__(app)
        self.max_upload_size = max_upload_size

    async def dispatch(self, request: Request, call_next):
        if request.headers.get('content-length'):
            try:
                content_length = int(request.headers['content-length'])
            except ValueError:
                content_length = 0
            if content_length > self.max_upload_size:
                return JSONResponse(
                    status_code=413,
                    content={"ok": False, "error": "Request entity too large. Max allowed size is 1MB."}
                )
        response = await call_next(request)
        return response

# Logging Middleware
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Log request safely without PII
        logger.info(f"Request started: {request.method} {request.url.path}")

        try:
            response = await call_next(request)
            process_time = (time.time() - start_time) * 1000
            
            # Mask paths that might contain PII or sensitive tokens?
            # Fastapi routes do not usually contain PII except possibly in UUIDs which are safe.
            logger.info(
                f"Request completed: {request.method} {request.url.path} "
                f"Status: {response.status_code} "
                f"Duration: {process_time:.2f}ms"
            )
            return response
        except Exception as e:
            process_time = (time.time() - start_time) * 1000
            logger.error(
                f"Request failed: {request.method} {request.url.path} "
                f"Duration: {process_time:.2f}ms "
                f"Error: {type(e).__name__}"
            )
            # Re-raise to let the global exception handler catch it
            raise
