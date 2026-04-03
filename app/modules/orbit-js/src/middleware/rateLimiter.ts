/**
 * Rate Limiting Middleware
 * 
 * Implements velocity and daily rate limits per user.
 * Ported from Python ratelimit.py
 */

import Redis from 'ioredis';
import { config } from '../config';
import { RateLimitInfo } from '../types';

/**
 * Rate limiter using Redis for distributed state
 */
export class RateLimiter {
  private redis: Redis;
  private dailyLimit: number;
  private velocityLimit: number;
  private velocityWindow: number;
  private enabled: boolean;

  constructor(redis?: Redis) {
    this.redis = redis || new Redis(config.redis.url, {
      retryStrategy: (times) => {
        const delay = Math.min(times * 50, 2000);
        return delay;
      },
      maxRetriesPerRequest: 3,
      lazyConnect: true,
    });

    this.dailyLimit = config.orbit.dailyChatLimit;
    this.velocityLimit = config.orbit.velocityLimit;
    this.velocityWindow = config.orbit.velocityWindow;
    this.enabled = config.rateLimit.enabled;
  }

  /**
   * Check both velocity and daily limits for a user
   * 
   * @param userId - User UUID
   * @returns Rate limit check result
   */
  async checkLimits(userId: string): Promise<{
    allowed: boolean;
    reason?: string;
    dailyRemaining: number;
    velocityRemaining: number;
    resetAt: Date;
  }> {
    if (!this.enabled) {
      return {
        allowed: true,
        dailyRemaining: this.dailyLimit,
        velocityRemaining: this.velocityLimit,
        resetAt: new Date(Date.now() + 24 * 60 * 60 * 1000),
      };
    }

    // Check velocity limit (requests per minute)
    const velocityKey = `rate:velocity:${userId}`;
    const velocityCount = await this.redis.incr(velocityKey);
    
    if (velocityCount === 1) {
      // First request, set expiry
      await this.redis.expire(velocityKey, this.velocityWindow);
    }

    if (velocityCount > this.velocityLimit) {
      const ttl = await this.redis.ttl(velocityKey);
      return {
        allowed: false,
        reason: `Rate limit exceeded. Try again in ${ttl} seconds.`,
        dailyRemaining: 0,
        velocityRemaining: 0,
        resetAt: new Date(Date.now() + ttl * 1000),
      };
    }

    // Check daily limit
    const dailyKey = `rate:daily:${userId}:${this.getCurrentDay()}`;
    const dailyCount = await this.redis.incr(dailyKey);
    
    if (dailyCount === 1) {
      // First request of the day, set expiry to end of day
      const secondsUntilMidnight = this.getSecondsUntilMidnight();
      await this.redis.expire(dailyKey, secondsUntilMidnight);
    }

    if (dailyCount > this.dailyLimit) {
      const secondsUntilMidnight = this.getSecondsUntilMidnight();
      return {
        allowed: false,
        reason: `Daily limit reached (${this.dailyLimit} requests). Reset at midnight.`,
        dailyRemaining: 0,
        velocityRemaining: this.velocityLimit - velocityCount,
        resetAt: new Date(Date.now() + secondsUntilMidnight * 1000),
      };
    }

    const dailyRemaining = this.dailyLimit - dailyCount;
    const velocityRemaining = this.velocityLimit - velocityCount;
    const secondsUntilMidnight = this.getSecondsUntilMidnight();

    return {
      allowed: true,
      dailyRemaining,
      velocityRemaining,
      resetAt: new Date(Date.now() + secondsUntilMidnight * 1000),
    };
  }

  /**
   * Get current day string (YYYY-MM-DD)
   */
  private getCurrentDay(): string {
    return new Date().toISOString().split('T')[0];
  }

  /**
   * Get seconds until midnight
   */
  private getSecondsUntilMidnight(): number {
    const now = new Date();
    const midnight = new Date(now);
    midnight.setHours(24, 0, 0, 0);
    return Math.floor((midnight.getTime() - now.getTime()) / 1000);
  }

  /**
   * Reset all rate limits for a user (for testing)
   */
  async resetLimits(userId: string): Promise<void> {
    const velocityKey = `rate:velocity:${userId}`;
    const dailyKey = `rate:daily:${userId}:${this.getCurrentDay()}`;
    
    await this.redis.del(velocityKey, dailyKey);
  }

  /**
   * Get current rate limit status for a user
   */
  async getStatus(userId: string): Promise<{
    dailyUsed: number;
    dailyRemaining: number;
    dailyLimit: number;
    velocityUsed: number;
    velocityRemaining: number;
    velocityLimit: number;
    resetAt: Date;
  }> {
    const dailyKey = `rate:daily:${userId}:${this.getCurrentDay()}`;
    const velocityKey = `rate:velocity:${userId}`;

    const [dailyUsed, velocityUsed] = await Promise.all([
      this.redis.get(dailyKey).then(v => parseInt(v || '0', 10)),
      this.redis.get(velocityKey).then(v => parseInt(v || '0', 10)),
    ]);

    return {
      dailyUsed,
      dailyRemaining: Math.max(0, this.dailyLimit - dailyUsed),
      dailyLimit: this.dailyLimit,
      velocityUsed,
      velocityRemaining: Math.max(0, this.velocityLimit - velocityUsed),
      velocityLimit: this.velocityLimit,
      resetAt: new Date(Date.now() + this.getSecondsUntilMidnight() * 1000),
    };
  }

  /**
   * Close Redis connection
   */
  async close(): Promise<void> {
    await this.redis.quit();
  }
}

// Singleton instance
let rateLimiterInstance: RateLimiter | null = null;

export function getRateLimiter(): RateLimiter {
  if (!rateLimiterInstance) {
    rateLimiterInstance = new RateLimiter();
  }
  return rateLimiterInstance;
}
