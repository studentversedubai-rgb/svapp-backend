"""
Redis Module

Manages Redis connection for caching and OTP storage.
"""

import os
from typing import Optional
import redis
from dotenv import load_dotenv

load_dotenv()

class RedisManager:
    """
    Manages Redis connection and operations
    """
    
    def __init__(self):
        """Initialize Redis connection"""
        self.redis_client: Optional[redis.Redis] = None
        self.memory_store = {} # Fallback for local dev when Redis is down
    
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
            print("INFO: Switching to IN-MEMORY storage (Dev Mode)")
            self.redis_client = None
    
    def disconnect(self):
        """Close Redis connection"""
        if self.redis_client:
            self.redis_client.close()
            print("INFO: Disconnected from Redis")
    
    def get(self, key: str) -> Optional[str]:
        """Get value from Redis or Memory"""
        if self.redis_client:
            return self.redis_client.get(key)
        return self.memory_store.get(key)
    
    def setex(self, key: str, time: int, value: str) -> bool:
        """Set value with expiration (seconds)"""
        if self.redis_client:
            return self.redis_client.setex(name=key, time=time, value=value)
        
        # In-memory fallback (ignores TTL for simplicity or could implement simple TTL)
        self.memory_store[key] = value
        print(f"DEBUG: Stored in Memory (No Redis): {key}={value}")
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
