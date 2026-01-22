# Architectural Decision Records (ADRs)

## Overview

This document records important architectural decisions made for the StudentVerse backend, including context, rationale, and consequences.

---

## ADR-001: Use FastAPI as Backend Framework

**Date:** 2026-01-22  
**Status:** Accepted

### Context
Need to choose a Python web framework for the backend API.

### Decision
Use FastAPI as the primary backend framework.

### Rationale
- **Performance**: FastAPI is one of the fastest Python frameworks (comparable to Node.js)
- **Async Support**: Native async/await for better concurrency
- **Type Safety**: Built-in Pydantic validation and type hints
- **Auto Documentation**: Automatic OpenAPI/Swagger documentation
- **Modern**: Uses latest Python features (3.11+)
- **Mobile-Friendly**: Excellent for REST APIs consumed by mobile apps

### Consequences
**Positive:**
- Fast development with auto-validation
- Excellent documentation out of the box
- Type safety reduces bugs
- Great performance for mobile apps

**Negative:**
- Team needs to learn FastAPI (if not familiar)
- Smaller ecosystem than Flask/Django

---

## ADR-002: Use Supabase for Auth and Database

**Date:** 2026-01-22  
**Status:** Accepted

### Context
Need authentication system and PostgreSQL database.

### Decision
Use Supabase for both authentication and database.

### Rationale
- **Integrated Solution**: Auth + Database in one platform
- **JWT Tokens**: Built-in JWT issuance and verification
- **No Password Storage**: Backend never handles passwords
- **PostgreSQL**: Robust, scalable database
- **Real-time**: Built-in real-time subscriptions (future use)
- **Cost-Effective**: Free tier sufficient for MVP

### Consequences
**Positive:**
- Faster development (no custom auth)
- Secure by default
- Scalable infrastructure
- Good developer experience

**Negative:**
- Vendor lock-in to Supabase
- Less control over auth flow
- Migration complexity if switching providers

**Mitigation:**
- Abstract database access with SQLAlchemy
- Keep business logic separate from Supabase specifics

---

## ADR-003: Make Email Immutable

**Date:** 2026-01-22  
**Status:** Accepted

### Context
Need to decide if users can change their email address.

### Decision
Email is **immutable** after registration and must be a university email.

### Rationale
- **Identity Consistency**: Email is primary identifier
- **University Verification**: Ensures student status
- **Security**: Prevents account takeover via email change
- **Simplicity**: No complex email change flow needed
- **Audit Trail**: Consistent user identity for analytics

### Consequences
**Positive:**
- Simpler security model
- Clear user identity
- No email change abuse

**Negative:**
- Users cannot change email if they graduate
- Support requests for email changes

**Mitigation:**
- Clear communication during onboarding
- Support process for exceptional cases (manual admin action)

---

## ADR-004: Use State Machine for Entitlements

**Date:** 2026-01-22  
**Status:** Accepted

### Context
Entitlements have complex lifecycle with multiple states and transitions.

### Decision
Implement state machine pattern for entitlement lifecycle management.

### Rationale
- **Business Logic Enforcement**: Prevents invalid state transitions
- **Clarity**: Clear definition of allowed transitions
- **Auditability**: All state changes logged
- **Reliability**: Reduces bugs in redemption flow
- **Scalability**: Easy to add new states/transitions

### States
- AVAILABLE → CLAIMED → RESERVED → REDEEMED
- Any state → EXPIRED or CANCELLED

### Consequences
**Positive:**
- Reliable redemption flow
- Clear business rules
- Easy to debug issues
- Prevents race conditions

**Negative:**
- More complex than simple status field
- Requires careful design

**Implementation:**
- `app/modules/entitlements/state_machine.py`
- All state transitions go through state machine
- Invalid transitions raise exceptions

---

## ADR-005: SV Orbit Uses Retrieval-Only Approach

**Date:** 2026-01-22  
**Status:** Accepted

### Context
SV Orbit needs to generate activity plans using AI.

### Decision
Use **retrieval-only** approach - LLM only formats presentation, never generates offer data.

### Rationale
- **No Hallucinations**: Only real partner offers suggested
- **Trust**: Users trust recommendations are real
- **Legal**: No liability for fake offers
- **Quality**: Partner data is curated and accurate
- **Control**: Full control over what's recommended

### Architecture
1. **Retrieval**: Search real offers from database
2. **Scoring**: Rank offers by relevance
3. **LLM**: Format presentation in natural language

### Consequences
**Positive:**
- 100% accurate recommendations
- No hallucination issues
- Legal safety
- User trust

**Negative:**
- Limited to existing partners
- Cannot suggest non-partner activities
- Requires good partner coverage

**Mitigation:**
- Onboard diverse partners
- Clear communication about partner-only recommendations

---

## ADR-006: Feature Flag SV Pay

**Date:** 2026-01-22  
**Status:** Accepted

### Context
Payment processing is planned but not ready for MVP.

### Decision
Include SV Pay module in codebase but disable via feature flag.

### Rationale
- **Future-Ready**: Structure exists for when needed
- **Parallel Development**: Can be developed alongside other features
- **Safe Deployment**: Won't activate until explicitly enabled
- **Clean Codebase**: Proper structure from day one

### Implementation
```python
FEATURE_SV_PAY_ENABLED = False  # Default disabled
```

### Consequences
**Positive:**
- Ready for future activation
- Clean architecture
- No rushed implementation

**Negative:**
- Unused code in production
- Maintenance overhead

**Mitigation:**
- Clear documentation that it's disabled
- Regular review to ensure it stays current

---

## ADR-007: Use Redis for Rate Limiting and Caching

**Date:** 2026-01-22  
**Status:** Accepted

### Context
Need rate limiting for OTP requests and caching for performance.

### Decision
Use Redis for both rate limiting and caching.

### Rationale
- **Performance**: In-memory, extremely fast
- **TTL Support**: Built-in expiration for rate limits and cache
- **Simplicity**: Single solution for multiple use cases
- **Scalability**: Easy to scale horizontally
- **Cost-Effective**: Lightweight and cheap

### Use Cases
- OTP rate limiting (per email)
- Session data (if needed)
- Cached offer listings
- Temporary data storage

### Consequences
**Positive:**
- Fast rate limiting
- Improved API performance
- Simple implementation

**Negative:**
- Additional infrastructure dependency
- Data loss if Redis crashes (acceptable for cache)

**Mitigation:**
- Use Redis only for ephemeral data
- Critical data always in PostgreSQL

---

## ADR-008: Deploy on Railway

**Date:** 2026-01-22  
**Status:** Accepted

### Context
Need hosting platform for production deployment.

### Decision
Deploy on Railway.

### Rationale
- **Simplicity**: Easy deployment from GitHub
- **Cost-Effective**: Reasonable pricing for startups
- **Integrated**: Database, Redis, and app in one platform
- **Auto-Deploy**: CI/CD built-in
- **Scalability**: Can scale as needed

### Consequences
**Positive:**
- Fast deployment
- Good developer experience
- Integrated monitoring

**Negative:**
- Vendor lock-in
- Less control than AWS/GCP

**Mitigation:**
- Use Docker for portability
- Keep infrastructure as code

---

## ADR-009: Use Pydantic for All Data Validation

**Date:** 2026-01-22  
**Status:** Accepted

### Context
Need consistent data validation across the application.

### Decision
Use Pydantic models for all request/response validation.

### Rationale
- **Type Safety**: Automatic type checking
- **Validation**: Built-in validators
- **Documentation**: Auto-generates OpenAPI schemas
- **FastAPI Integration**: Native support
- **Developer Experience**: Clear error messages

### Implementation
- All request bodies use Pydantic models
- All response bodies use Pydantic models
- Shared base models in `app/shared/schemas/`

### Consequences
**Positive:**
- Fewer validation bugs
- Better API documentation
- Clear contracts

**Negative:**
- Learning curve for Pydantic
- Verbose for simple endpoints

---

## ADR-010: Separate Modules by Domain

**Date:** 2026-01-22  
**Status:** Accepted

### Context
Need to organize code for 2 developers working in parallel.

### Decision
Use domain-driven module structure with clear boundaries.

### Rationale
- **Parallel Development**: Developers can work on different modules
- **Clear Ownership**: Each module has clear responsibility
- **Maintainability**: Easy to find and modify code
- **Scalability**: Can split into microservices later if needed
- **Testing**: Easier to test isolated modules

### Structure
```
app/modules/
  ├── auth/
  ├── users/
  ├── offers/
  ├── entitlements/
  ├── validation/
  ├── analytics/
  ├── orbit/
  └── pay/
```

### Consequences
**Positive:**
- Clean code organization
- Parallel development
- Easy to navigate

**Negative:**
- Some code duplication
- Cross-module dependencies need management

**Mitigation:**
- Shared utilities in `app/shared/`
- Clear module interfaces
- Minimize cross-module dependencies

---

## Future ADRs

As the project evolves, document new decisions here:
- ADR-011: [Future decision]
- ADR-012: [Future decision]

---

**Last Updated**: 2026-01-22
