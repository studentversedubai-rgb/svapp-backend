/**
 * SV Orbit JavaScript Service
 * 
 * Entry point for the Orbit AI service using Vercel AI SDK.
 */

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

// Health check endpoint (no auth required)
app.get('/health', healthHandler);
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

app.listen(PORT, () => {
  console.log(`
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║           SV Orbit AI Service (JavaScript)                 ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝

🚀 Server running on port ${PORT}
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
