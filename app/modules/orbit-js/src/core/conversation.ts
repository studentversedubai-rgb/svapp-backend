/**
 * Conversation Memory Manager for Orbit
 * 
 * Manages conversation history for contextual AI responses.
 * Uses Redis for fast, temporary storage with session-based isolation.
 * Ported from Python conversation.py
 */

import Redis from 'ioredis';
import { config } from '../config';
import { ConversationMessage } from '../types';

/**
 * Conversation manager using Redis
 * 
 * Storage format:
 * - Key: orbit:conversation:{user_id}:{session_id}
 * - Value: JSON list of messages
 * - TTL: 24 hours (configurable)
 */
export class ConversationManager {
  private redis: Redis;
  private ttlSeconds: number;
  private maxMessages: number;
  private keyPrefix: string = 'orbit:conversation';

  constructor(redis?: Redis) {
    this.redis = redis || new Redis(config.redis.url, {
      retryStrategy: (times) => {
        const delay = Math.min(times * 50, 2000);
        return delay;
      },
      maxRetriesPerRequest: 3,
      lazyConnect: true,
    });
    
    this.ttlSeconds = config.conversation.ttlSeconds;
    this.maxMessages = config.conversation.maxMessages;
  }

  /**
   * Generate Redis key for conversation
   */
  private getKey(userId: string, sessionId: string): string {
    return `${this.keyPrefix}:${userId}:${sessionId}`;
  }

  /**
   * Add message to conversation history
   * 
   * @param userId - User UUID
   * @param sessionId - Session UUID
   * @param role - 'user' or 'assistant'
   * @param content - Message content
   * @returns True if successful
   */
  async addMessage(
    userId: string,
    sessionId: string,
    role: 'user' | 'assistant',
    content: string
  ): Promise<boolean> {
    try {
      const key = this.getKey(userId, sessionId);
      
      // Create message object
      const message: ConversationMessage = {
        role,
        content,
        timestamp: new Date().toISOString(),
      };

      // Get existing history
      const historyJson = await this.redis.get(key);
      let history: ConversationMessage[] = [];
      
      if (historyJson) {
        history = JSON.parse(historyJson);
      }

      // Append new message
      history.push(message);

      // Keep only last N messages to save memory
      if (history.length > this.maxMessages) {
        history = history.slice(-this.maxMessages);
      }

      // Save back to Redis with TTL
      await this.redis.setex(key, this.ttlSeconds, JSON.stringify(history));

      return true;
    } catch (error) {
      console.error('Failed to add message to conversation:', error);
      return false;
    }
  }

  /**
   * Get conversation history
   * 
   * @param userId - User UUID
   * @param sessionId - Session UUID
   * @param limit - Maximum number of messages to return (most recent)
   * @returns List of messages in chronological order
   */
  async getHistory(
    userId: string,
    sessionId: string,
    limit?: number
  ): Promise<ConversationMessage[]> {
    try {
      const key = this.getKey(userId, sessionId);
      const historyJson = await this.redis.get(key);

      if (!historyJson) {
        return [];
      }

      let history: ConversationMessage[] = JSON.parse(historyJson);

      // Apply limit if specified
      if (limit && history.length > limit) {
        history = history.slice(-limit);
      }

      return history;
    } catch (error) {
      console.error('Failed to get conversation history:', error);
      return [];
    }
  }

  /**
   * Clear conversation history for a session
   * 
   * @param userId - User UUID
   * @param sessionId - Session UUID
   * @returns True if successful
   */
  async clearSession(userId: string, sessionId: string): Promise<boolean> {
    try {
      const key = this.getKey(userId, sessionId);
      await this.redis.del(key);
      return true;
    } catch (error) {
      console.error('Failed to clear conversation:', error);
      return false;
    }
  }

  /**
   * Get number of messages in conversation
   */
  async getMessageCount(userId: string, sessionId: string): Promise<number> {
    const history = await this.getHistory(userId, sessionId);
    return history.length;
  }

  /**
   * Format conversation history for LLM consumption (OpenAI format)
   * 
   * Returns list of {role: "user"/"assistant", content: "..."}
   */
  async formatHistoryForLLM(
    userId: string,
    sessionId: string,
    limit: number = 10
  ): Promise<Array<{ role: 'user' | 'assistant'; content: string }>> {
    const history = await this.getHistory(userId, sessionId, limit);
    
    // Convert to OpenAI message format (remove timestamps)
    return history.map((msg) => ({
      role: msg.role,
      content: msg.content,
    }));
  }

  /**
   * Check if a session exists
   */
  async sessionExists(userId: string, sessionId: string): Promise<boolean> {
    const key = this.getKey(userId, sessionId);
    const exists = await this.redis.exists(key);
    return exists === 1;
  }

  /**
   * Get all active sessions for a user
   */
  async getUserSessions(userId: string): Promise<string[]> {
    try {
      const pattern = `${this.keyPrefix}:${userId}:*`;
      const keys = await this.redis.keys(pattern);
      
      // Extract session IDs from keys
      return keys.map((key) => {
        const parts = key.split(':');
        return parts[parts.length - 1];
      });
    } catch (error) {
      console.error('Failed to get user sessions:', error);
      return [];
    }
  }

  /**
   * Close Redis connection
   */
  async close(): Promise<void> {
    await this.redis.quit();
  }
}

// Singleton instance
let conversationManagerInstance: ConversationManager | null = null;

export function getConversationManager(): ConversationManager {
  if (!conversationManagerInstance) {
    conversationManagerInstance = new ConversationManager();
  }
  return conversationManagerInstance;
}
