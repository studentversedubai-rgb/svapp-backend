# SV Orbit JavaScript Service

AI-powered conversational offer discovery service using Vercel AI SDK and OpenRouter.

## Overview

This is a JavaScript/TypeScript implementation of the Orbit AI service, replacing the Python backend for AI-related functionality. It uses the Vercel AI SDK for streaming chat responses and tool calling.

## Features

- **Streaming Chat**: Real-time AI responses with streaming support
- **Intent Analysis**: Automatically detects if user wants offers or just chatting
- **Offer Retrieval**: Fetches relevant offers from Supabase database
- **Distance Calculation**: Haversine formula for location-based sorting
- **Conversation Memory**: Redis-based session storage (24h TTL)
- **Circuit Breaker**: Automatic failover after consecutive failures
- **Rate Limiting**: Per-user velocity and daily limits
- **Multi-mode Support**: CHAT, FIND, and PLAN modes

## Architecture

```
src/
├── api/
│   └── chat.ts           # Main streaming chat endpoint
├── lib/
│   ├── conversation.ts   # Redis conversation manager
│   ├── distance.ts       # Haversine distance calculation
│   ├── prompts.ts        # System prompts (ported from Python)
│   └── retrieval.ts      # Supabase offer retrieval
├── middleware/
│   ├── auth.ts           # JWT authentication
│   ├── circuitBreaker.ts # Circuit breaker pattern
│   └── rateLimiter.ts    # Rate limiting with Redis
├── config/
│   └── index.ts          # Environment configuration
├── types/
│   ├── index.ts          # TypeScript interfaces
│   └── schemas.ts        # Zod validation schemas
└── index.ts              # Express app entry point
```

## Setup

### 1. Install Dependencies

```bash
npm install
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Required environment variables:
- `OPENROUTER_API_KEY` - Your OpenRouter API key
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_SERVICE_KEY` - Supabase service role key
- `REDIS_URL` - Redis connection URL
- `JWT_SECRET` - Secret for JWT validation

### 3. Build

```bash
npm run build
```

### 4. Run

Development:
```bash
npm run dev
```

Production:
```bash
npm start
```

## API Endpoints

### Health Check
```
GET /health
GET /orbit/health
```

### Chat
```
POST /orbit/chat
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "message": "Find me coffee shops",
  "session_id": "optional-session-id",
  "latitude": 25.2048,
  "longitude": 55.2708,
  "mode": "find"
}
```

Modes:
- `chat` - Casual conversation (default)
- `find` - Focused offer discovery
- `plan` - Structured itinerary creation

## Migration from Python

This service replaces the Python `app/modules/orbit/` functionality:

| Python File | JavaScript Equivalent |
|-------------|----------------------|
| `router.py` | `src/api/chat.ts` |
| `service.py` | Logic in `chat.ts` handler |
| `llm.py` | Vercel AI SDK + OpenRouter |
| `conversation.py` | `src/lib/conversation.ts` |
| `retrieval.py` | `src/lib/retrieval.ts` |
| `schemas.py` | `src/types/` |
| `prompts.py` | `src/lib/prompts.ts` |
| `distance.py` | `src/lib/distance.ts` |

## Deployment

### Railway

1. Create a new Railway project
2. Connect your GitHub repository
3. Add environment variables in Railway dashboard
4. Deploy

The service will start on port defined by `PORT` environment variable (default: 3000).

### Docker

```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
```

## Differences from Python Version

1. **Streaming**: JavaScript version streams responses token-by-token
2. **No tools yet**: Tool calling implementation simplified - direct function calls used
3. **Same Redis**: Uses same Redis instance as Python for conversation history
4. **Same Supabase**: Uses same Supabase database for offers
5. **JWT compatible**: Validates same JWT tokens as Python backend

## Testing

```bash
# Health check
curl http://localhost:3000/health

# Chat (requires valid JWT)
curl -X POST http://localhost:3000/orbit/chat \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Find me coffee",
    "mode": "find",
    "latitude": 25.2048,
    "longitude": 55.2708
  }'
```

## Monitoring

- Circuit breaker state: Check logs for "Circuit breaker OPEN"
- Rate limits: 429 responses when exceeded
- Errors: 500 responses with circuit breaker tracking

## Future Enhancements

1. Add proper tool calling with Vercel AI SDK tools
2. Add streaming JSON parsing for structured responses
3. Add OpenTelemetry tracing
4. Add metrics endpoint for monitoring
