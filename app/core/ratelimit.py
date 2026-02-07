"""
Rate Limiting Module

Redis-based rate limiting for Orbit chat endpoints.
Implements velocity and daily quota protection to prevent abuse and control API costs.
"""

import logging
from datetime import datetime
from fastapi import HTTPException
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
        """
        Check velocity limit (spam protection)
        
        Uses Redis INCR with EXPIRE for atomic operations.
        
        Args:
            user_id: User UUID
            
        Raises:
            HTTPException 429: If velocity limit exceeded
        """
        key = f"limit:velocity:{user_id}"
        
        try:
            if redis_manager.redis_client:
                # Redis is available - use atomic operations
                current = redis_manager.redis_client.get(key)
                
                if current is None:
                    # First request in window - initialize counter
                    redis_manager.redis_client.setex(key, cls.VELOCITY_WINDOW, "1")
                else:
                    # Increment counter
                    count = int(current)
                    
                    if count >= cls.VELOCITY_LIMIT:
                        logger.warning(f"Velocity limit exceeded for user {user_id}")
                        raise HTTPException(
                            status_code=429,
                            detail="Whoa there! 🐢 You're typing too fast! Slow down and try again in a moment."
                        )
                    
                    # Increment (without resetting TTL)
                    redis_manager.redis_client.incr(key)
            else:
                # Fallback to in-memory (for dev mode)
                current = redis_manager.memory_store.get(key)
                
                if current is None:
                    redis_manager.memory_store[key] = 1
                else:
                    count = int(current)
                    
                    if count >= cls.VELOCITY_LIMIT:
                        logger.warning(f"Velocity limit exceeded for user {user_id} (memory mode)")
                        raise HTTPException(
                            status_code=429,
                            detail="Whoa there! 🐢 You're typing too fast! Slow down and try again in a moment."
                        )
                    
                    redis_manager.memory_store[key] = count + 1
                    
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error checking velocity limit: {e}")
            # Fail open - don't block user if rate limiting fails
            pass
    
    @classmethod
    def _check_daily_quota(cls, user_id: str, daily_limit: int) -> None:
        """
        Check daily quota limit
        
        Uses date-based keys to track daily usage.
        
        Args:
            user_id: User UUID
            daily_limit: Maximum requests per day
            
        Raises:
            HTTPException 429: If daily quota exceeded
        """
        # Use current date as part of key
        date_string = datetime.utcnow().strftime("%Y-%m-%d")
        key = f"limit:daily:{user_id}:{date_string}"
        
        try:
            if redis_manager.redis_client:
                # Redis is available - use atomic operations
                current = redis_manager.redis_client.get(key)
                
                if current is None:
                    # First request today - initialize counter
                    redis_manager.redis_client.setex(key, cls.DAILY_WINDOW, "1")
                else:
                    # Increment counter
                    count = int(current)
                    
                    if count >= daily_limit:
                        logger.warning(f"Daily quota exceeded for user {user_id}")
                        raise HTTPException(
                            status_code=429,
                            detail=f"You've reached your daily AI chat limit ({daily_limit} messages). 😴 Come back tomorrow for more amazing recommendations!"
                        )
                    
                    # Increment (without resetting TTL)
                    redis_manager.redis_client.incr(key)
            else:
                # Fallback to in-memory (for dev mode)
                current = redis_manager.memory_store.get(key)
                
                if current is None:
                    redis_manager.memory_store[key] = 1
                else:
                    count = int(current)
                    
                    if count >= daily_limit:
                        logger.warning(f"Daily quota exceeded for user {user_id} (memory mode)")
                        raise HTTPException(
                            status_code=429,
                            detail=f"You've reached your daily AI chat limit ({daily_limit} messages). 😴 Come back tomorrow for more amazing recommendations!"
                        )
                    
                    redis_manager.memory_store[key] = count + 1
                    
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error checking daily quota: {e}")
            # Fail open - don't block user if rate limiting fails
            pass
    
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
                velocity_count = redis_manager.memory_store.get(velocity_key, 0)
                daily_count = redis_manager.memory_store.get(daily_key, 0)
            
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
