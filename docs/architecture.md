# StudentVerse Backend Architecture

## Overview

StudentVerse backend is a production-grade FastAPI application designed to support a mobile app (iOS & Android) built with React Native. The architecture follows domain-driven design principles with clear separation of concerns.

## System Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────┐
│                   Mobile Apps (iOS/Android)              │
│                     React Native                         │
└────────────────────┬────────────────────────────────────┘
                     │ HTTPS/REST
                     ▼
┌─────────────────────────────────────────────────────────┐
│                  FastAPI Backend (Railway)               │
│  ┌──────────┬──────────┬──────────┬──────────────────┐ │
│  │   Auth   │  Offers  │Entitle-  │  SV Orbit (AI)   │ │
│  │          │          │  ments   │                  │ │
│  └──────────┴──────────┴──────────┴──────────────────┘ │
└────────────┬──────────────────────┬────────────────────┘
             │                      │
             ▼                      ▼
┌─────────────────────┐  ┌──────────────────┐
│  Supabase           │  │     Redis        │
│  - PostgreSQL       │  │  - Caching       │
│  - Auth (JWT)       │  │  - Rate Limiting │
└─────────────────────┘  └──────────────────┘
```

## Core Principles

### 1. Domain-Driven Design
- Each module is isolated and self-contained
- Clear boundaries between domains
- Minimal cross-module dependencies

### 2. Mobile-First Authentication
- JWT-based authentication via Supabase
- Persistent login with refresh tokens
- No password storage in backend
- University email validation (immutable)

### 3. State Machine Pattern
- Entitlements use state machine for lifecycle management
- Ensures valid state transitions
- Prevents invalid operations

### 4. Feature Flags
- SV Pay disabled by default
- SV Orbit can be toggled
- Analytics can be enabled/disabled

## Module Architecture

### Core Modules (`app/core/`)
Shared infrastructure and utilities:
- **config.py**: Environment configuration
- **security.py**: JWT verification (Supabase)
- **database.py**: Supabase + PostgreSQL connection
- **redis.py**: Redis connection and operations
- **logging.py**: Structured logging setup

### Shared Layer (`app/shared/`)
Cross-cutting concerns:
- **schemas/**: Base Pydantic models
- **enums/**: Type-safe enumerations
- **utils/**: Helper functions
- **constants.py**: Application constants

### Domain Modules (`app/modules/`)

#### 1. Auth Module
- OTP-based authentication
- User registration
- Token refresh
- **No password storage** (Supabase handles this)

#### 2. Users Module
- User profile management
- **Email is immutable** after registration
- Role-based access control

#### 3. Offers Module
- Partner offer listing
- Offer claiming
- Category filtering

#### 4. Entitlements Module (CORE)
- **State machine-driven lifecycle**
- States: AVAILABLE → CLAIMED → RESERVED → REDEEMED
- QR code generation
- Expiry management

#### 5. Validation Module
- Validator PWA support
- QR code scanning
- Redemption confirmation

#### 6. Analytics Module
- Event tracking
- User statistics
- Partner metrics

#### 7. SV Orbit Module (AI Planner)
- **Retrieval-only** (no hallucinations)
- Scoring + orchestration
- LLM presentation layer
- Partner-only recommendations

#### 8. SV Pay Module (Feature Flagged)
- Payment processing (disabled)
- PSP abstraction layer
- Transaction management

## Data Flow Examples

### Offer Claiming Flow
```
1. User browses offers (Offers Module)
2. User claims offer (Offers Module)
3. Entitlement created in CLAIMED state (Entitlements Module)
4. Analytics event tracked (Analytics Module)
```

### Redemption Flow
```
1. User reserves entitlement (Entitlements Module)
   - State: CLAIMED → RESERVED
   - QR code generated
2. Validator scans QR (Validation Module)
3. Validator confirms redemption (Validation Module)
   - State: RESERVED → REDEEMED
4. Analytics event tracked (Analytics Module)
```

### SV Orbit Flow
```
1. User requests plan (e.g., "date night")
2. Retrieval service finds relevant offers (Retrieval)
3. Offers scored for relevance (Service)
4. LLM formats presentation (LLM)
5. Plan returned to user
```

## Technology Stack

### Backend Framework
- **FastAPI**: Modern, fast, async Python framework
- **Pydantic**: Data validation and settings
- **SQLAlchemy**: ORM for database operations

### Database & Auth
- **Supabase**: PostgreSQL + Auth service
- **Redis**: Caching and rate limiting

### Deployment
- **Railway**: Hosting platform
- **Docker**: Containerization
- **Uvicorn**: ASGI server

### External Services
- **Supabase Auth**: JWT issuance and verification
- **OpenAI** (optional): LLM for SV Orbit
- **Stripe** (future): Payment processing

## Security Architecture

### Authentication
1. User requests OTP via Supabase Auth
2. OTP sent to university email
3. User verifies OTP
4. Supabase issues JWT tokens
5. Backend verifies JWT on each request

### Authorization
- Role-based access control (RBAC)
- User roles: student, validator, admin
- Route-level permission checks

### Data Protection
- University email validation
- Email immutability
- Rate limiting on sensitive endpoints
- Input validation via Pydantic

## Scalability Considerations

### Horizontal Scaling
- Stateless API design
- Redis for shared state
- Database connection pooling

### Performance
- Async/await throughout
- Redis caching for frequently accessed data
- Database indexes on common queries
- Pagination for large result sets

### Monitoring
- Structured logging (JSON format)
- Health check endpoint
- Error tracking and alerting

## Development Workflow

### Adding a New Feature
1. Create schemas in `schemas.py`
2. Define models in `models.py` (if database changes needed)
3. Implement service logic in `service.py`
4. Create API routes in `router.py`
5. Register router in `main.py`
6. Write tests
7. Update documentation

### Database Changes
1. Create migration in `migrations/`
2. Test migration locally
3. Apply to staging
4. Apply to production

## Deployment Architecture

### Railway Configuration
- Automatic deployment on push to `main`
- Environment variables managed in Railway dashboard
- Health checks configured
- Auto-restart on failure

### Environment Separation
- **Development**: Local with `.env`
- **Staging**: Railway preview deployments
- **Production**: Railway production environment

## Future Enhancements

### Phase 2 Features
- SV Pay activation
- Advanced analytics
- Partner dashboard
- Admin panel

### Scalability Improvements
- Message queue for async tasks
- CDN for static assets
- Database read replicas
- Microservices split (if needed)

---

**Last Updated**: 2026-01-22
