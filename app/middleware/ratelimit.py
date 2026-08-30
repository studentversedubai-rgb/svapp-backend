"""
Rate Limiting Module

Redis-based rate limiting for Orbit chat endpoints.
Implements velocity and daily quota protection to prevent abuse and control API costs.
"""

import hashlib
import logging
import os
import time
from datetime import datetime
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.redis import redis_manager

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Redis-based rate limiter with two protection layers:
    1. Velocity protection: Prevents spam (10 req/60s)
    2. Daily quota: Prevents excessive usage (150 req/24h)
    """
    
    # Velocity limits (spam protection)
    VELOCITY_LIMIT = 10  # Max requests
    VELOCITY_WINDOW = 60  # Time window in seconds
    
    # Daily quota limits
    DAILY_LIMIT = 150  # Max requests per day (overridable via settings)
    DAILY_WINDOW = 86400  # 24 hours in seconds
    
    @classmethod
    def check_limits(cls, user_id: str, daily_limit: int = None) -> None:
        """
        Check rate limits for a user. Raises HTTPException if exceeded.
        
        Args:
            user_id: User UUID
            daily_limit: Optional override for daily limit (from settings)
            
        Raises:
            HTTPException 429: If rate limit is exceeded
        """
        # Use provided daily limit or default
        daily_limit = daily_limit or cls.DAILY_LIMIT
        
        # Check velocity limit first (faster to compute)
        cls._check_velocity_limit(user_id)
        
        # Check daily quota
        cls._check_daily_quota(user_id, daily_limit)
    
    @classmethod
    def _check_velocity_limit(cls, user_id: str) -> None:
        """Spam protection. Raises HTTPException 429 if exceeded."""
        cls.check_generic_limit(
            f"limit:velocity:{user_id}",
            cls.VELOCITY_LIMIT,
            cls.VELOCITY_WINDOW,
            error_message="Whoa there! 🐢 You're typing too fast! Slow down and try again in a moment.",
        )

    @classmethod
    def _check_daily_quota(cls, user_id: str, daily_limit: int) -> None:
        """Daily quota. Raises HTTPException 429 if exceeded."""
        date_string = datetime.utcnow().strftime("%Y-%m-%d")
        cls.check_generic_limit(
            f"limit:daily:{user_id}:{date_string}",
            daily_limit,
            cls.DAILY_WINDOW,
            error_message=f"You've reached your daily AI chat limit ({daily_limit} messages). 😴 Come back tomorrow for more amazing recommendations!",
        )

    @classmethod
    def get_remaining(cls, user_id: str, daily_limit: int = None) -> dict:
        """
        Get remaining quota for user (for debugging/monitoring)
        
        Args:
            user_id: User UUID
            daily_limit: Optional override for daily limit
            
        Returns:
            Dict with remaining velocity and daily quota
        """
        daily_limit = daily_limit or cls.DAILY_LIMIT
        date_string = datetime.utcnow().strftime("%Y-%m-%d")
        
        velocity_key = f"limit:velocity:{user_id}"
        daily_key = f"limit:daily:{user_id}:{date_string}"
        
        try:
            # Get current counts
            velocity_count = 0
            daily_count = 0
            
            if redis_manager.redis_client:
                velocity_current = redis_manager.redis_client.get(velocity_key)
                daily_current = redis_manager.redis_client.get(daily_key)
                
                velocity_count = int(velocity_current) if velocity_current else 0
                daily_count = int(daily_current) if daily_current else 0
            else:
                velocity_raw = redis_manager.get(velocity_key)
                daily_raw = redis_manager.get(daily_key)

                velocity_count = int(velocity_raw) if velocity_raw else 0
                daily_count = int(daily_raw) if daily_raw else 0
            
            return {
                "velocity_remaining": max(0, cls.VELOCITY_LIMIT - velocity_count),
                "velocity_limit": cls.VELOCITY_LIMIT,
                "daily_remaining": max(0, daily_limit - daily_count),
                "daily_limit": daily_limit
            }
        except Exception as e:
            logger.error(f"Error getting remaining quota: {e}")
            return {
                "velocity_remaining": cls.VELOCITY_LIMIT,
                "velocity_limit": cls.VELOCITY_LIMIT,
                "daily_remaining": daily_limit,
                "daily_limit": daily_limit
            }

    # Atomic INCR + EXPIRE. Guarantees a key NEVER exists without a TTL,
    # which is what caused permanent lockouts: a plain INCR on a key that
    # expired between GET and INCR recreates it with no expiry, so the
    # counter climbs forever and waiting never clears it.
    _LUA_INCR = """
    local c = redis.call('INCR', KEYS[1])
    local t = redis.call('TTL', KEYS[1])
    if c == 1 or t < 0 then
        redis.call('EXPIRE', KEYS[1], ARGV[1])
        t = tonumber(ARGV[1])
    end
    return {c, t}
    """
    _lua_sha = None

    @classmethod
    def _incr_redis(cls, key: str, window: int):
        """Atomically increment `key` and return (count, ttl). Never leaves key TTL-less."""
        client = redis_manager.redis_client
        try:
            if cls._lua_sha is None:
                cls._lua_sha = client.script_load(cls._LUA_INCR)
            count, ttl = client.evalsha(cls._lua_sha, 1, key, window)
        except Exception:
            # NOSCRIPT after a Redis restart/failover, or EVAL unsupported.
            cls._lua_sha = None
            pipe = client.pipeline()
            pipe.incr(key)
            pipe.ttl(key)
            count, ttl = pipe.execute()
            if count == 1 or ttl is None or ttl < 0:
                client.expire(key, window)
                ttl = window
        return int(count), int(ttl)

    @classmethod
    def _incr_memory(cls, key: str, window: int):
        """Dev-mode fallback. Uses redis_manager's TTL-aware helpers, not the raw dict."""
        current = redis_manager.get(key)
        if current is None:
            redis_manager.setex(key, window, "1")
            return 1, window
        count = int(current) + 1
        _, expiry = redis_manager.memory_store[key]
        ttl = max(1, int(expiry - time.time())) if expiry else window
        redis_manager.memory_store[key] = (str(count), expiry)
        return count, ttl

    @classmethod
    def check_generic_limit(
        cls,
        key: str,
        limit: int,
        window: int,
        error_message: str = "Too Many Requests"
    ) -> dict:
        """
        Fixed-window rate limit check. Counts the current request.

        Returns rate limit metadata for response headers.
        Raises HTTPException 429 when the limit is exceeded.
        """
        try:
            if redis_manager.redis_client:
                count, ttl = cls._incr_redis(key, window)
            else:
                count, ttl = cls._incr_memory(key, window)
        except Exception as e:
            logger.error(f"Error checking generic limit for {key}: {e}")
            # Fail open - a broken limiter must not take the API down.
            return {"limit": limit, "remaining": limit, "reset": window}

        if ttl <= 0:
            ttl = window

        if count > limit:
            logger.warning(f"Rate limit exceeded for key {key} ({count}/{limit}, resets in {ttl}s)")
            raise HTTPException(
                status_code=429,
                detail=error_message,
                headers={
                    "Retry-After": str(ttl),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(ttl),
                },
            )

        return {"limit": limit, "remaining": max(0, limit - count), "reset": ttl}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-identity request limiting.

    Identity is the caller's bearer token when present, and only falls back to
    IP otherwise. Keying purely on IP puts every customer behind a single
    carrier-grade NAT (a whole mobile ISP, an office, a mall wifi) into one
    shared bucket, so a handful of users lock out thousands.
    """

    # Paths that must never be limited.
    EXEMPT_PATHS = frozenset({
        "/", "/docs", "/redoc", "/openapi.json",
        "/health", "/healthz", "/ready", "/metrics", "/favicon.ico",
    })

    AUTH_STRICT_PREFIXES = (
        "/auth/send-otp",
        "/auth/verify-otp",
        "/auth/login",
        "/auth/manual-signup",
        "/auth/signup/verify-microsoft",
        "/auth/forgot-password/verify-microsoft",
    )

    # Number of trusted proxies that append to X-Forwarded-For. The real client
    # is the Nth entry from the right; anything further left is attacker-supplied
    # and must not be trusted, or clients can spoof their way past the limiter.
    PROXY_HOPS = int(os.getenv("RATE_LIMIT_PROXY_HOPS", "1"))

    # A single app screen fans out to 5-6 endpoints, so the general budget has to
    # absorb bursts. Tune via env without a redeploy.
    GENERAL_LIMIT = int(os.getenv("RATE_LIMIT_PER_MINUTE", "300"))
    AUTH_LIMIT = int(os.getenv("RATE_LIMIT_AUTH_PER_MIN", "10"))
    PAYMENT_LIMIT = int(os.getenv("RATE_LIMIT_PAYMENT_PER_MIN", "20"))
    ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() not in ("false", "0", "no")

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if not self.ENABLED or request.method == "OPTIONS" or path in self.EXEMPT_PATHS:
            return await call_next(request)

        is_auth_strict = path.startswith(self.AUTH_STRICT_PREFIXES)
        is_payment = path.startswith("/payments")

        ip = self._get_ip(request)

        if is_auth_strict:
            # Credential endpoints stay keyed on IP - that is the abuse vector -
            # but the window is per endpoint so OTP and login do not share a budget.
            limit, window = self.AUTH_LIMIT, 60
            key = f"rl:auth:{path}:{ip}"
        elif is_payment:
            limit, window = self.PAYMENT_LIMIT, 60
            key = f"rl:pay:{self._identity(request, ip)}"
        else:
            limit, window = self.GENERAL_LIMIT, 60
            key = f"rl:global:{self._identity(request, ip)}"

        try:
            info = RateLimiter.check_generic_limit(
                key, limit, window,
                error_message="Too many requests. Please try again in a moment.",
            )
        except HTTPException as e:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=429,
                content={"ok": False, "error": e.detail},
                headers=e.headers,
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
        response.headers["X-RateLimit-Reset"] = str(info["reset"])
        return response

    def _identity(self, request: Request, ip: str) -> str:
        """Bearer token when authenticated, else IP. Token is hashed, never logged raw."""
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and len(auth) > 20:
            digest = hashlib.sha256(auth[7:].strip().encode()).hexdigest()[:24]
            return f"t:{digest}"
        return f"ip:{ip}"

    def _get_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            parts = [p.strip() for p in forwarded.split(",") if p.strip()]
            if parts:
                # Count back from the right past our own trusted proxies.
                idx = max(0, len(parts) - max(1, self.PROXY_HOPS))
                return parts[idx]
        return getattr(request.client, "host", "127.0.0.1")
