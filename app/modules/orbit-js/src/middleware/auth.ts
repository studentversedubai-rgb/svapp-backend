/**
 * Authentication Middleware
 * 
 * Validates JWT tokens and extracts user context.
 */

import { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';
import { config } from '../config';
import { UserContext } from '../types';

// Extend Express Request type to include user
declare global {
  namespace Express {
    interface Request {
      user?: UserContext;
    }
  }
}

/**
 * JWT Authentication middleware
 * Validates Bearer token and attaches user to request
 */
export function authMiddleware(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  try {
    // Get authorization header
    const authHeader = req.headers.authorization;
    
    if (!authHeader) {
      res.status(401).json({
        error: 'Unauthorized',
        message: 'Authorization header is required',
      });
      return;
    }

    // Check Bearer format
    const parts = authHeader.split(' ');
    if (parts.length !== 2 || parts[0] !== 'Bearer') {
      res.status(401).json({
        error: 'Unauthorized',
        message: 'Authorization header must be Bearer token',
      });
      return;
    }

    const token = parts[1];

    // Verify JWT
    try {
      const decoded = jwt.verify(token, config.jwt.secret) as UserContext;
      req.user = decoded;
      next();
    } catch (jwtError) {
      res.status(401).json({
        error: 'Unauthorized',
        message: 'Invalid or expired token',
      });
      return;
    }
  } catch (error) {
    console.error('Auth middleware error:', error);
    res.status(500).json({
      error: 'Internal Server Error',
      message: 'Authentication check failed',
    });
    return;
  }
}

/**
 * Optional auth middleware
 * Attaches user if token valid, but doesn't reject if missing/invalid
 */
export function optionalAuthMiddleware(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  try {
    const authHeader = req.headers.authorization;
    
    if (!authHeader) {
      next();
      return;
    }

    const parts = authHeader.split(' ');
    if (parts.length !== 2 || parts[0] !== 'Bearer') {
      next();
      return;
    }

    const token = parts[1];

    try {
      const decoded = jwt.verify(token, config.jwt.secret) as UserContext;
      req.user = decoded;
    } catch {
      // Invalid token, continue without user
    }
    
    next();
  } catch (error) {
    // Continue without user on error
    next();
  }
}

/**
 * Extract user ID from request
 * Returns null if no authenticated user
 */
export function getUserId(req: Request): string | null {
  return req.user?.id || null;
}

/**
 * Require user middleware
 * Ensures request has authenticated user
 */
export function requireUser(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  if (!req.user?.id) {
    res.status(401).json({
      error: 'Unauthorized',
      message: 'Authentication required',
    });
    return;
  }
  next();
}
