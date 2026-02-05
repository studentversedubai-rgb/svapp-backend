# Phase 3 Deployment Checklist

## Pre-Deployment

### Environment Setup
- [ ] Verify `.env` has all required variables:
  - [ ] `SUPABASE_URL`
  - [ ] `SUPABASE_SERVICE_KEY`
  - [ ] `REDIS_URL`
  - [ ] `RESEND_API_KEY` (for notifications)
  - [ ] `RESEND_FROM`

### Dependencies
- [ ] Install/update Python dependencies:
  ```bash
  pip install -r requirements.txt
  ```

### Code Review
- [ ] Review all Phase 3 files:
  - [ ] `app/modules/entitlements/models.py`
  - [ ] `app/modules/entitlements/schemas.py`
  - [ ] `app/modules/entitlements/state_machine.py`
  - [ ] `app/modules/entitlements/service.py`
  - [ ] `app/modules/entitlements/router.py`
  - [ ] `app/shared/enums/__init__.py`
  - [ ] `app/shared/constants.py`
  - [ ] `app/main.py`

- [ ] Verify NO modifications to Phase 1/2 code:
  - [ ] `app/modules/auth/` - unchanged
  - [ ] `app/modules/users/` - unchanged
  - [ ] `app/modules/offers/` - unchanged

---

## Database Migration

### 1. Generate SQL
- [ ] Run migration script:
  ```bash
  python migrations/phase3_setup.py
  ```

### 2. Review SQL
- [ ] Review generated SQL statements
- [ ] Verify table schemas
- [ ] Check index definitions
- [ ] Validate RLS policies

### 3. Execute Migration
- [ ] Open Supabase Dashboard
- [ ] Go to SQL Editor
- [ ] Copy all SQL statements
- [ ] Execute SQL
- [ ] Verify no errors

### 4. Verify Tables
- [ ] Check `entitlements` table exists
- [ ] Check `redemptions` table exists
- [ ] Check `analytics_events` table exists
- [ ] Verify indexes created:
  ```sql
  SELECT * FROM pg_indexes WHERE tablename IN ('entitlements', 'redemptions');
  ```

### 5. Verify RLS Policies
- [ ] Check RLS enabled on `entitlements`
- [ ] Check RLS enabled on `redemptions`
- [ ] Verify user policies work
- [ ] Verify service role policies work

### 6. Test Database
- [ ] Insert test entitlement:
  ```sql
  INSERT INTO entitlements (user_id, offer_id, state, expires_at)
  VALUES ('test-user', 'test-offer', 'active', NOW() + INTERVAL '1 day');
  ```
- [ ] Query test entitlement
- [ ] Delete test entitlement

---

## Redis Verification

### 1. Test Connection
- [ ] Run connection test:
  ```bash
  python -c "from app.core.redis import redis_manager; redis_manager.connect()"
  ```
- [ ] Verify output: "INFO: Connected to Redis"

### 2. Test Operations
- [ ] Test SET operation:
  ```python
  from app.core.redis import redis_manager
  redis_manager.connect()
  redis_manager.setex("test:key", 60, "test-value")
  ```
- [ ] Test GET operation:
  ```python
  value = redis_manager.get("test:key")
  print(value)  # Should print: test-value
  ```
- [ ] Test DELETE operation:
  ```python
  redis_manager.delete("test:key")
  ```

### 3. Verify Namespacing
- [ ] Check Redis keys use correct prefixes:
  - [ ] `sv:app:redeem:token:*`
  - [ ] `sv:app:claim:daily:*`
  - [ ] `sv:app:otp:*` (existing)

---

## Testing

### 1. Unit Tests
- [ ] Run all Phase 3 tests:
  ```bash
  pytest tests/test_entitlements_phase3.py -v
  ```
- [ ] Verify all tests pass
- [ ] Check test coverage:
  ```bash
  pytest tests/test_entitlements_phase3.py --cov=app.modules.entitlements
  ```

### 2. Integration Tests
- [ ] Test complete redemption flow:
  1. [ ] Claim entitlement
  2. [ ] Generate QR token
  3. [ ] Validate token
  4. [ ] Confirm redemption
  5. [ ] Verify savings calculation

### 3. State Machine Tests
- [ ] Test valid transitions
- [ ] Test invalid transitions
- [ ] Test void window enforcement
- [ ] Test terminal states

### 4. Fraud Prevention Tests
- [ ] Test daily limit enforcement
- [ ] Test token expiry
- [ ] Test token reuse rejection
- [ ] Test device binding

---

## API Testing

### 1. Start Server
- [ ] Start development server:
  ```bash
  uvicorn app.main:app --reload --port 8000
  ```
- [ ] Verify server starts without errors
- [ ] Check logs for warnings

### 2. Swagger UI
- [ ] Open http://localhost:8000/docs
- [ ] Verify all Phase 3 endpoints visible:
  - [ ] `POST /entitlements/claim`
  - [ ] `POST /entitlements/{id}/proof`
  - [ ] `POST /entitlements/validate`
  - [ ] `POST /entitlements/confirm`
  - [ ] `POST /entitlements/void`
  - [ ] `GET /entitlements/my`
  - [ ] `GET /entitlements/savings`

### 3. Postman Testing
- [ ] Import Postman collection:
  - File: `StudentVerse-Phase3-Redemption.postman_collection.json`
- [ ] Set environment variables:
  - [ ] `base_url`: http://localhost:8000
  - [ ] `jwt_token`: (get from auth endpoint)
  - [ ] `offer_id`: (get from offers endpoint)

- [ ] Run test scenarios:
  1. [ ] **Happy Path**
     - [ ] Claim entitlement → 200 OK
     - [ ] Generate QR → 200 OK, token returned
     - [ ] Validate → 200 OK, PASS
     - [ ] Confirm → 200 OK, redemption created
  
  2. [ ] **Token Expiry**
     - [ ] Generate QR → 200 OK
     - [ ] Wait 31 seconds
     - [ ] Validate → 200 OK, FAIL (expired)
  
  3. [ ] **Token Reuse**
     - [ ] Validate token → 200 OK, PASS
     - [ ] Validate same token → 200 OK, FAIL (already used)
  
  4. [ ] **Daily Limit**
     - [ ] Claim offer → 200 OK
     - [ ] Claim same offer → 400 Bad Request
  
  5. [ ] **Void Logic**
     - [ ] Confirm redemption → 200 OK
     - [ ] Void within 2 hours → 200 OK
     - [ ] Try void after 2 hours → 400 Bad Request

### 4. Error Handling
- [ ] Test with invalid JWT → 401 Unauthorized
- [ ] Test with missing fields → 422 Validation Error
- [ ] Test with invalid UUIDs → 400 Bad Request
- [ ] Test with expired entitlement → 400 Bad Request

---

## Security Verification

### 1. Authentication
- [ ] All endpoints require JWT
- [ ] Endpoints reject requests without Authorization header
- [ ] Endpoints reject invalid JWTs
- [ ] User ID derived from JWT, not request body

### 2. Authorization
- [ ] Users can only access their own entitlements
- [ ] Users cannot access other users' data
- [ ] RLS policies enforce row-level security

### 3. Token Security
- [ ] QR tokens expire in 30 seconds
- [ ] Tokens are single-use
- [ ] Tokens stored securely in Redis
- [ ] Tokens deleted after validation

### 4. Input Validation
- [ ] All request bodies validated by Pydantic
- [ ] Decimal amounts validated (max 2 decimal places)
- [ ] UUIDs validated
- [ ] Enum values validated

---

## Performance Testing

### 1. Load Testing
- [ ] Test concurrent claims (100 users)
- [ ] Test QR token generation rate (1000/min)
- [ ] Test validation throughput
- [ ] Monitor Redis memory usage

### 2. Response Times
- [ ] Claim entitlement: < 200ms
- [ ] Generate QR: < 100ms
- [ ] Validate token: < 150ms
- [ ] Confirm redemption: < 300ms

### 3. Database Performance
- [ ] Check query execution times
- [ ] Verify indexes are used
- [ ] Monitor connection pool

---

## Monitoring Setup

### 1. Logging
- [ ] Verify logs are being written
- [ ] Check log levels (INFO, WARNING, ERROR)
- [ ] Test error logging

### 2. Metrics
- [ ] Set up monitoring for:
  - [ ] Token generation rate
  - [ ] Validation success rate
  - [ ] Token expiry rate
  - [ ] Void rate
  - [ ] Average savings

### 3. Alerts
- [ ] Configure alerts for:
  - [ ] High error rate
  - [ ] High void rate (> 5%)
  - [ ] Token generation spike (> 1000/min)
  - [ ] Redis connection failures

---

## Documentation Review

### 1. API Documentation
- [ ] Review `docs/phase3_redemption.md`
- [ ] Verify all endpoints documented
- [ ] Check example requests/responses
- [ ] Validate error codes

### 2. Deployment Docs
- [ ] Review `PHASE3_README.md`
- [ ] Verify deployment steps
- [ ] Check troubleshooting guide

### 3. Quick Reference
- [ ] Review `PHASE3_QUICK_REFERENCE.md`
- [ ] Verify flow diagrams
- [ ] Check code examples

---

## Staging Deployment

### 1. Deploy to Staging
- [ ] Push code to staging branch
- [ ] Trigger deployment pipeline
- [ ] Verify deployment successful

### 2. Smoke Tests
- [ ] Test health endpoint
- [ ] Test auth endpoints (Phase 1)
- [ ] Test offers endpoints (Phase 2)
- [ ] Test entitlements endpoints (Phase 3)

### 3. End-to-End Testing
- [ ] Complete redemption flow
- [ ] Test with real mobile app
- [ ] Verify QR code rendering
- [ ] Test merchant validation flow

### 4. Data Verification
- [ ] Check entitlements created
- [ ] Verify redemptions recorded
- [ ] Validate analytics events
- [ ] Review savings calculations

---

## Production Deployment

### 1. Pre-Production
- [ ] Backup production database
- [ ] Review staging test results
- [ ] Get approval from stakeholders

### 2. Database Migration
- [ ] Run migration on production DB
- [ ] Verify tables created
- [ ] Check RLS policies
- [ ] Test with service role

### 3. Deploy Code
- [ ] Push to production branch
- [ ] Trigger deployment
- [ ] Monitor deployment logs
- [ ] Verify no errors

### 4. Post-Deployment
- [ ] Run smoke tests
- [ ] Test critical paths
- [ ] Monitor error rates
- [ ] Check Redis connection

### 5. Rollback Plan
- [ ] Document rollback steps
- [ ] Keep previous version ready
- [ ] Monitor for 24 hours

---

## Post-Deployment Monitoring

### First Hour
- [ ] Monitor error rates
- [ ] Check API response times
- [ ] Verify Redis operations
- [ ] Review logs for warnings

### First Day
- [ ] Track redemption count
- [ ] Monitor void rate
- [ ] Check token expiry rate
- [ ] Verify analytics data

### First Week
- [ ] Review user feedback
- [ ] Analyze redemption patterns
- [ ] Check merchant satisfaction
- [ ] Optimize based on metrics

---

## Success Criteria

### Technical
- [ ] All tests passing
- [ ] Zero Phase 1/2 regressions
- [ ] API response times < targets
- [ ] Error rate < 1%

### Business
- [ ] Redemptions working end-to-end
- [ ] Savings calculated correctly
- [ ] Void logic functioning
- [ ] Analytics data accurate

### Security
- [ ] All endpoints authenticated
- [ ] No security vulnerabilities
- [ ] RLS policies enforced
- [ ] Token security verified

---

## Sign-Off

### Development Team
- [ ] Backend Engineer: _________________ Date: _______
- [ ] QA Engineer: _________________ Date: _______

### Stakeholders
- [ ] Product Manager: _________________ Date: _______
- [ ] Tech Lead: _________________ Date: _______

---

## Notes

**Deployment Date:** _______________________

**Deployed By:** _______________________

**Issues Encountered:**
- 
- 
- 

**Resolutions:**
- 
- 
- 

**Next Steps:**
- 
- 
- 

---

**Status:** ⬜ Not Started | 🟡 In Progress | ✅ Complete | ❌ Failed

**Overall Progress:** _____ / _____ items complete
