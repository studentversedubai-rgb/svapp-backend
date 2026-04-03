/**
 * SV Orbit JavaScript Service
 *
 * Entry point for the Orbit AI service using Vercel AI SDK.
 */

// Catch any crash during startup so Railway logs show what happened
process.on('uncaughtException', (err) => {
  console.error('UNCAUGHT EXCEPTION — app crashed:', err);
  process.exit(1);
});
process.on('unhandledRejection', (reason) => {
  console.error('UNHANDLED REJECTION:', reason);
});

console.log('[STARTUP] Loading modules...');
console.log('[STARTUP] PORT env =', process.env.PORT);
console.log('[STARTUP] NODE_ENV =', process.env.NODE_ENV);
console.log('[STARTUP] REDIS_URL set =', !!process.env.REDIS_URL);
console.log('[STARTUP] SUPABASE_URL set =', !!process.env.SUPABASE_URL);
console.log('[STARTUP] OPENROUTER_API_KEY set =', !!process.env.OPENROUTER_API_KEY);
console.log('[STARTUP] JWT_SECRET set =', !!process.env.JWT_SECRET);

import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import { config } from './config';
import { chatHandler, healthHandler } from './api/chat';
import { authMiddleware } from './middleware/auth';
import { getCircuitBreaker } from './middleware/circuitBreaker';

// Initialize Express app
const app = express();

// Security middleware
app.use(helmet());
app.use(cors({
  origin: process.env.CORS_ORIGIN || '*',
  methods: ['GET', 'POST'],
  allowedHeaders: ['Content-Type', 'Authorization'],
}));

// Body parsing middleware
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true }));

// Request logging middleware
app.use((req, res, next) => {
  const timestamp = new Date().toISOString();
  console.log(`[${timestamp}] ${req.method} ${req.path} - ${req.ip}`);
  next();
});

// Root health check — always returns 200, no dependencies
app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'orbit', timestamp: new Date().toISOString() });
});

// Detailed health check with service status
app.get('/orbit/health', healthHandler);

// Orbit chat endpoint (requires auth)
app.post('/orbit/chat', authMiddleware, chatHandler);

// Error handling middleware
app.use((err: Error, req: express.Request, res: express.Response, next: express.NextFunction) => {
  console.error('Error:', err);
  
  // Check if headers already sent
  if (res.headersSent) {
    return next(err);
  }

  res.status(500).json({
    error: 'Internal Server Error',
    message: config.isDevelopment ? err.message : 'Something went wrong',
  });
});

// 404 handler
app.use((req, res) => {
  res.status(404).json({
    error: 'Not Found',
    message: `Endpoint ${req.path} not found`,
  });
});

// Start server
const PORT = config.port;
const HOST = '0.0.0.0';

const server = app.listen(PORT, HOST, () => {
  console.log(`
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║           SV Orbit AI Service (JavaScript)                 ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝

🚀 Server running on http://${HOST}:${PORT}
📁 Environment: ${config.nodeEnv}
🤖 AI Model: ${config.openrouter.model}
🔧 Features:
   - Circuit Breaker: ${config.circuitBreaker.failureThreshold} failures / ${config.circuitBreaker.cooldownSeconds}s cooldown
   - Rate Limit: ${config.orbit.velocityLimit} req/min, ${config.orbit.dailyChatLimit} req/day
   - Conversation TTL: ${config.conversation.ttlSeconds}s

Endpoints:
   GET  /health          - Health check
   GET  /orbit/health    - Health check (same as above)
   POST /orbit/chat      - Chat with Orbit AI (requires Bearer token)
  `);
});

server.on('error', (error: any) => {
  console.error('Server failed to start:', error.message);
  process.exit(1);
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('SIGTERM received, shutting down gracefully');
  process.exit(0);
});

process.on('SIGINT', () => {
  console.log('SIGINT received, shutting down gracefully');
  process.exit(0);
});

export default app;
