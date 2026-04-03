/**
 * Circuit Breaker Middleware
 * 
 * Prevents cascading failures by temporarily disabling the service
 * after consecutive failures.
 * Ported from Python router.py circuit breaker logic.
 */

import { config } from '../config';

/**
 * Circuit breaker state management
 */
class CircuitBreaker {
  private failures: number = 0;
  private openUntil: number = 0;
  private threshold: number;
  private cooldownSeconds: number;

  constructor(
    threshold: number = config.circuitBreaker.failureThreshold,
    cooldownSeconds: number = config.circuitBreaker.cooldownSeconds
  ) {
    this.threshold = threshold;
    this.cooldownSeconds = cooldownSeconds;
  }

  /**
   * Check if circuit is currently open
   */
  isOpen(): boolean {
    const now = Date.now() / 1000; // Convert to seconds
    if (now < this.openUntil) {
      return true;
    }
    
    // If cooldown period passed, reset the circuit
    if (this.openUntil > 0 && now >= this.openUntil) {
      this.reset();
    }
    
    return false;
  }

  /**
   * Get remaining seconds until circuit closes
   */
  getRemainingSeconds(): number {
    if (!this.isOpen()) return 0;
    return Math.max(0, Math.ceil(this.openUntil - Date.now() / 1000));
  }

  /**
   * Record a failure
   */
  recordFailure(): void {
    this.failures++;
    
    if (this.failures >= this.threshold) {
      this.openUntil = Date.now() / 1000 + this.cooldownSeconds;
      console.error(`Circuit breaker OPEN after ${this.failures} failures. Will retry in ${this.cooldownSeconds}s`);
    }
  }

  /**
   * Record a success and reset failures
   */
  recordSuccess(): void {
    if (this.failures > 0) {
      this.reset();
    }
  }

  /**
   * Reset circuit breaker state
   */
  reset(): void {
    this.failures = 0;
    this.openUntil = 0;
  }

  /**
   * Get current state for monitoring
   */
  getState(): {
    isOpen: boolean;
    failures: number;
    openUntil: number | null;
    remainingSeconds: number;
  } {
    return {
      isOpen: this.isOpen(),
      failures: this.failures,
      openUntil: this.openUntil > 0 ? this.openUntil : null,
      remainingSeconds: this.getRemainingSeconds(),
    };
  }
}

// Singleton instance for the orbit service
let circuitBreakerInstance: CircuitBreaker | null = null;

export function getCircuitBreaker(): CircuitBreaker {
  if (!circuitBreakerInstance) {
    circuitBreakerInstance = new CircuitBreaker();
  }
  return circuitBreakerInstance;
}

export { CircuitBreaker };
