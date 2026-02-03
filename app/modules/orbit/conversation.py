"""
Conversation Memory Manager for Orbit

Manages conversation history for contextual AI responses.
Uses Redis for fast, temporary storage with session-based isolation.
"""

import json
import logging
from typing import List, Dict, Optional
from datetime import datetime
from app.core.redis import redis_manager

logger = logging.getLogger(__name__)


class ConversationManager:
    """
    Manages conversation history in Redis
    
    Storage format:
    - Key: orbit:conversation:{user_id}:{session_id}
    - Value: JSON list of messages
    - TTL: 24 hours
    """
    
    def __init__(self, ttl_seconds: int = 86400):  # 24 hours default
        """Initialize conversation manager"""
        self.ttl_seconds = ttl_seconds
        self.key_prefix = "orbit:conversation"
    
    def _get_key(self, user_id: str, session_id: str) -> str:
        """Generate Redis key for conversation"""
        return f"{self.key_prefix}:{user_id}:{session_id}"
    
    def add_message(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str
    ) -> bool:
        """
        Add message to conversation history
        
        Args:
            user_id: User UUID
            session_id: Session UUID
            role: 'user' or 'assistant'
            content: Message content
            
        Returns:
            True if successful
        """
        try:
            key = self._get_key(user_id, session_id)
            
            # Create message object
            message = {
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Get existing history
            history_json = redis_manager.get(key)
            
            if history_json:
                history = json.loads(history_json)
            else:
                history = []
            
            # Append new message
            history.append(message)
            
            # Keep only last 20 messages (10 turns) to save memory
            if len(history) > 20:
                history = history[-20:]
            
            # Save back to Redis with TTL
            redis_manager.setex(
                key,
                self.ttl_seconds,
                json.dumps(history)
            )
            
            logger.debug(f"Added {role} message to conversation {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add message to conversation: {e}")
            return False
    
    def get_history(
        self,
        user_id: str,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Get conversation history
        
        Args:
            user_id: User UUID
            session_id: Session UUID
            limit: Maximum number of messages to return (most recent)
            
        Returns:
            List of messages in chronological order
        """
        try:
            key = self._get_key(user_id, session_id)
            history_json = redis_manager.get(key)
            
            if not history_json:
                return []
            
            history = json.loads(history_json)
            
            # Apply limit if specified
            if limit and len(history) > limit:
                history = history[-limit:]
            
            return history
            
        except Exception as e:
            logger.error(f"Failed to get conversation history: {e}")
            return []
    
    def clear_session(self, user_id: str, session_id: str) -> bool:
        """
        Clear conversation history for a session
        
        Args:
            user_id: User UUID
            session_id: Session UUID
            
        Returns:
            True if successful
        """
        try:
            key = self._get_key(user_id, session_id)
            redis_manager.delete(key)
            logger.info(f"Cleared conversation session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear conversation: {e}")
            return False
    
    def get_message_count(self, user_id: str, session_id: str) -> int:
        """Get number of messages in conversation"""
        history = self.get_history(user_id, session_id)
        return len(history)
    
    def format_history_for_llm(
        self,
        user_id: str,
        session_id: str,
        limit: int = 10
    ) -> List[Dict[str, str]]:
        """
        Format conversation history for LLM consumption (OpenAI format)
        
        Returns:
            List of {"role": "user"/"assistant", "content": "..."}
        """
        history = self.get_history(user_id, session_id, limit)
        
        # Convert to OpenAI message format (remove timestamps)
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in history
        ]


# Singleton instance
conversation_manager = ConversationManager()
