"""
Redis Module

Manages Redis connection for caching and OTP storage.
"""

import os
from typing import Optional, Dict
import redis
import time
from dotenv import load_dotenv

load_dotenv()

class RedisManager:
    """
    Manages Redis connection and operations
    """
    
    def __init__(self):
        """Initialize Redis connection"""
        self.redis_client: Optional[redis.Redis] = None
        self.memory_store: Dict[str, tuple[str, Optional[float]]] = {}  # {key: (value, expiry_timestamp)}
    
    def connect(self):
        """
        Establish connection to Redis
        """
        redis_url = os.getenv("REDIS_URL")
        # Ensure we try to connect even if URL looks internal, but handle failure gracefully
        try:
            self.redis_client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=2  # Short timeout for local dev
            )
            # Test connection
            self.redis_client.ping()
            print("INFO: Connected to Redis")
        except Exception as e:
            print(f"WARNING: Failed to connect to Redis: {e}")
            print("INFO: Switching to IN-MEMORY storage (Dev Mode) - TTL supported")
            self.redis_client = None
    
    def disconnect(self):
        """Close Redis connection"""
        if self.redis_client:
            self.redis_client.close()
            print("INFO: Disconnected from Redis")
    
    def _clean_expired_memory_keys(self):
        """Remove expired keys from memory store"""
        now = time.time()
        expired_keys = [
            key for key, (_, expiry) in self.memory_store.items()
            if expiry and expiry < now
        ]
        for key in expired_keys:
            del self.memory_store[key]
    
    def get(self, key: str) -> Optional[str]:
        """Get value from Redis or Memory"""
        if self.redis_client:
            return self.redis_client.get(key)
        
        # Memory fallback with TTL check
        self._clean_expired_memory_keys()
        entry = self.memory_store.get(key)
        if entry:
            value, expiry = entry
            if expiry is None or expiry > time.time():
                return value
            # Key expired
            del self.memory_store[key]
        return None
    
    def setex(self, key: str, ttl: int, value: str) -> bool:
        """Set value with expiration (seconds)"""
        if self.redis_client:
            return self.redis_client.setex(name=key, time=ttl, value=value)
        
        # In-memory fallback WITH TTL support
        expiry = time.time() + ttl if ttl > 0 else None
        self.memory_store[key] = (value, expiry)
        print(f"DEBUG: Stored in Memory with TTL {ttl}s: {key}={value}")
        return True
    
    def delete(self, key: str) -> bool:
        """Delete key from Redis or Memory"""
        if self.redis_client:
            return bool(self.redis_client.delete(key))
        
        if key in self.memory_store:
            del self.memory_store[key]
            return True
        return False

# Global Redis manager instance
redis_manager = RedisManager()

def get_redis_client():
    """Dependency to get Redis client"""
    return redis_manager.redis_client
