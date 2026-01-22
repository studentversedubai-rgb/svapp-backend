# StudentVerse Backend Development Phases

## Overview

This document outlines the backend development phases for StudentVerse. Each phase builds upon the previous one, with clear deliverables and success criteria.

---

## Phase 0A: Foundation (Weeks 1-2)

### Goal
Establish core infrastructure and basic authentication

### Deliverables

#### 1. Infrastructure Setup
- [x] Repository structure created
- [ ] Railway deployment configured
- [ ] Supabase project created
- [ ] Redis instance provisioned
- [ ] Environment variables configured

#### 2. Core Modules
- [ ] `app/core/config.py` - Configuration management
- [ ] `app/core/security.py` - JWT verification
- [ ] `app/core/database.py` - Supabase connection
- [ ] `app/core/redis.py` - Redis connection
- [ ] `app/core/logging.py` - Logging setup

#### 3. Authentication Module
- [ ] OTP generation and sending
- [ ] OTP verification
- [ ] User registration
- [ ] Token refresh
- [ ] University email validation
- [ ] Rate limiting

#### 4. Users Module
- [ ] User profile CRUD
- [ ] Email immutability enforcement
- [ ] Last login tracking

### Success Criteria
- ✅ Mobile app can register with university email
- ✅ Mobile app can login with OTP
- ✅ JWT tokens work for authenticated requests
- ✅ User profile can be retrieved and updated
- ✅ Deployed to Railway and accessible

### API Endpoints
```
POST   /api/v1/auth/send-otp
POST   /api/v1/auth/verify-otp
POST   /api/v1/auth/refresh
POST   /api/v1/auth/logout
GET    /api/v1/users/me
PATCH  /api/v1/users/me
```

---

## Phase 0B: Core Features (Weeks 3-4)

### Goal
Implement offers and entitlements with state machine

### Deliverables

#### 1. Offers Module
- [ ] Offer model and database schema
- [ ] List offers with filters
- [ ] Get offer details
- [ ] Claim offer (creates entitlement)
- [ ] Partner management (admin)

#### 2. Entitlements Module (CORE)
- [ ] Entitlement model and database schema
- [ ] State machine implementation
- [ ] State transitions:
  - [ ] CLAIMED (on offer claim)
  - [ ] RESERVED (user prepares to redeem)
  - [ ] REDEEMED (validator confirms)
  - [ ] EXPIRED (time-based)
  - [ ] CANCELLED (user/admin action)
- [ ] QR code generation
- [ ] Expiry management

#### 3. Validation Module
- [ ] QR code scanning
- [ ] Entitlement validation
- [ ] Redemption confirmation
- [ ] Validator history

### Success Criteria
- ✅ Students can browse and claim offers
- ✅ Entitlements created with correct state
- ✅ State machine prevents invalid transitions
- ✅ QR codes generated for redemption
- ✅ Validators can scan and redeem
- ✅ All state transitions logged

### API Endpoints
```
GET    /api/v1/offers
GET    /api/v1/offers/{id}
POST   /api/v1/offers/{id}/claim
GET    /api/v1/entitlements/my
GET    /api/v1/entitlements/{id}
POST   /api/v1/entitlements/{id}/reserve
POST   /api/v1/entitlements/{id}/redeem
POST   /api/v1/entitlements/{id}/cancel
POST   /api/v1/validation/scan
POST   /api/v1/validation/redeem
GET    /api/v1/validation/history
```

---

## Phase 1: SV Orbit - AI Planner (Weeks 5-6)

### Goal
Implement AI-powered activity planner with retrieval-only approach

### Deliverables

#### 1. Retrieval System
- [ ] Offer search by keywords
- [ ] Offer search by category
- [ ] Semantic search (optional)
- [ ] User-based recommendations

#### 2. Scoring Algorithm
- [ ] Relevance scoring
- [ ] Category matching
- [ ] User history consideration
- [ ] Popularity weighting

#### 3. LLM Integration
- [ ] OpenAI API integration
- [ ] Prompt engineering for plan presentation
- [ ] Response formatting
- [ ] Error handling

#### 4. Orbit Service
- [ ] Plan generation orchestration
- [ ] Plan storage
- [ ] Feedback collection
- [ ] Scoring improvement based on feedback

### Success Criteria
- ✅ Users can request activity plans
- ✅ Plans contain only real partner offers
- ✅ LLM presents plans naturally
- ✅ No hallucinated data
- ✅ Feedback improves recommendations

### API Endpoints
```
POST   /api/v1/orbit/plans
GET    /api/v1/orbit/plans/{id}
POST   /api/v1/orbit/plans/{id}/feedback
```

### Constraints
- **Retrieval-only**: No hallucinated offers
- **Partner data only**: Only suggest existing partners
- **Transparent**: Explain why each offer was selected

---

## Phase 1.5: Analytics & Insights (Week 7)

### Goal
Track usage and provide insights

### Deliverables

#### 1. Event Tracking
- [ ] Offer views
- [ ] Offer claims
- [ ] Entitlement redemptions
- [ ] User login/signup
- [ ] Orbit plan generation
- [ ] Payment events (when enabled)

#### 2. User Statistics
- [ ] Total offers claimed
- [ ] Total redemptions
- [ ] Estimated savings
- [ ] Activity timeline

#### 3. Partner Analytics
- [ ] Offer performance metrics
- [ ] Conversion rates
- [ ] Redemption rates
- [ ] Popular offers

### Success Criteria
- ✅ All user actions tracked
- ✅ Users can see their statistics
- ✅ Partners can see their metrics
- ✅ Data used for Orbit improvements

### API Endpoints
```
POST   /api/v1/analytics/track
GET    /api/v1/analytics/user-stats
GET    /api/v1/analytics/partner-stats/{id}
```

---

## Phase 2: SV Pay - Payments (Future)

### Goal
Enable payment processing (feature flagged)

### Status
**DISABLED BY DEFAULT** - Present in codebase but inactive

### Deliverables (When Enabled)

#### 1. Payment Infrastructure
- [ ] PSP integration (Stripe/PayPal)
- [ ] Issuer abstraction layer
- [ ] Transaction model
- [ ] Webhook handling

#### 2. Payment Flow
- [ ] Payment initiation
- [ ] Payment status tracking
- [ ] Refund processing
- [ ] Transaction history

#### 3. Security
- [ ] Webhook signature verification
- [ ] PCI compliance considerations
- [ ] Secure token handling

### Success Criteria (Future)
- ✅ Users can initiate payments
- ✅ Payment status tracked accurately
- ✅ Webhooks processed reliably
- ✅ Refunds work correctly
- ✅ All transactions logged

### API Endpoints (Disabled)
```
POST   /api/v1/pay/initiate
GET    /api/v1/pay/transactions
POST   /api/v1/pay/webhook
```

### Activation Checklist
- [ ] Choose PSP (Stripe, PayPal, etc.)
- [ ] Set up PSP account
- [ ] Configure webhook URLs
- [ ] Test in sandbox environment
- [ ] Enable feature flag: `FEATURE_SV_PAY_ENABLED=true`
- [ ] Deploy to production

---

## Cross-Phase Considerations

### Testing
Each phase should include:
- Unit tests for services
- Integration tests for API endpoints
- E2E tests for critical flows
- Load testing for performance

### Documentation
Each phase should update:
- API documentation (Swagger/ReDoc)
- Architecture diagrams
- Deployment guides
- Frontend integration guides

### Deployment
Each phase should:
- Deploy to staging first
- Run smoke tests
- Get stakeholder approval
- Deploy to production
- Monitor for issues

### Team Collaboration

#### For 2 Backend Developers

**Developer 1 Focus:**
- Phase 0A: Core infrastructure + Auth
- Phase 0B: Offers module
- Phase 1: Orbit retrieval + scoring
- Phase 1.5: Analytics

**Developer 2 Focus:**
- Phase 0A: Users module
- Phase 0B: Entitlements + Validation
- Phase 1: Orbit LLM + orchestration
- Phase 2: SV Pay (when enabled)

**Collaboration Points:**
- Daily standups
- Code reviews on all PRs
- Shared documentation updates
- Integration testing together

---

## Timeline Summary

| Phase | Duration | Key Deliverable |
|-------|----------|-----------------|
| 0A | 2 weeks | Auth + Users working |
| 0B | 2 weeks | Offers + Entitlements working |
| 1 | 2 weeks | SV Orbit working |
| 1.5 | 1 week | Analytics working |
| 2 | TBD | SV Pay (future) |

**Total MVP**: 7 weeks

---

## Success Metrics

### Phase 0A
- 100% auth tests passing
- <200ms average response time
- Zero auth-related bugs

### Phase 0B
- State machine 100% reliable
- QR codes scannable 100% of time
- <500ms offer listing

### Phase 1
- Plans generated in <3 seconds
- 0% hallucinated offers
- >80% user satisfaction with plans

### Phase 1.5
- All events tracked
- Analytics dashboard functional
- <100ms analytics queries

---

**Last Updated**: 2026-01-22
