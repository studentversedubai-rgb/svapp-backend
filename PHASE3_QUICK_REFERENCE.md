# Phase 3 Quick Reference Guide

## Redemption Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    STUDENT APP (Mobile)                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 1. Browse offers
                              ▼
                    ┌──────────────────┐
                    │  Select Offer    │
                    └──────────────────┘
                              │
                              │ 2. POST /entitlements/claim
                              ▼
                    ┌──────────────────┐
                    │  Entitlement     │
                    │  Created         │
                    │  State: ACTIVE   │
                    └──────────────────┘
                              │
                              │ 3. Ready to redeem
                              │    POST /entitlements/{id}/proof
                              ▼
                    ┌──────────────────┐
                    │  QR Token        │
                    │  Generated       │
                    │  TTL: 30s        │
                    └──────────────────┘
                              │
                              │ 4. Display QR code
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    MERCHANT PWA (Web)                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 5. Scan QR code
                              │    POST /entitlements/validate
                              ▼
                    ┌──────────────────┐
                    │  Validation      │
                    │  PASS/FAIL       │
                    │  State: PENDING  │
                    └──────────────────┘
                              │
                              │ 6. Enter bill amount
                              │    POST /entitlements/confirm
                              ▼
                    ┌──────────────────┐
                    │  Redemption      │
                    │  Confirmed       │
                    │  State: USED     │
                    └──────────────────┘
                              │
                              │ 7. Notification sent
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STUDENT APP (Mobile)                          │
│                "You saved AED 20.00!"                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## API Call Sequence

### Student Claims Offer

```http
POST /entitlements/claim
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
  "offer_id": "uuid",
  "device_id": "device-123"
}

Response 200:
{
  "success": true,
  "entitlement_id": "ent-uuid",
  "offer_id": "offer-uuid",
  "expires_at": "2026-02-01T23:59:59Z"
}
```

### Student Generates QR

```http
POST /entitlements/{entitlement_id}/proof
Authorization: Bearer {jwt_token}

Response 200:
{
  "success": true,
  "proof_token": "secure-random-token-32-chars",
  "expires_at": "2026-02-01T15:45:30Z",
  "ttl_seconds": 30
}
```

**Frontend Action:** Render QR code from `proof_token`

### Merchant Scans QR

```http
POST /entitlements/validate
Authorization: Bearer {merchant_jwt_token}
Content-Type: application/json

{
  "proof_token": "secure-random-token-32-chars"
}

Response 200 (Success):
{
  "success": true,
  "status": "PASS",
  "entitlement_id": "ent-uuid",
  "offer_title": "20% Off All Items",
  "offer_type": "percentage",
  "discount_value": "20%",
  "merchant_name": "Coffee Shop",
  "student_name": "John Doe"
}

Response 200 (Failure):
{
  "success": false,
  "status": "FAIL",
  "reason": "Invalid or expired token"
}
```

### Merchant Confirms Redemption

```http
POST /entitlements/confirm
Authorization: Bearer {merchant_jwt_token}
Content-Type: application/json

{
  "entitlement_id": "ent-uuid",
  "total_bill_amount": 100.00,
  "discounted_amount": 80.00  // Optional
}

Response 200:
{
  "success": true,
  "redemption_id": "red-uuid",
  "entitlement_id": "ent-uuid",
  "total_bill": 100.00,
  "discount_amount": 20.00,
  "final_amount": 80.00,
  "savings": 20.00,
  "redeemed_at": "2026-02-01T15:46:00Z"
}
```

### Void Redemption (If Needed)

```http
POST /entitlements/void
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
  "entitlement_id": "ent-uuid",
  "reason": "Customer returned item"
}

Response 200:
{
  "success": true,
  "entitlement_id": "ent-uuid",
  "voided_at": "2026-02-01T16:00:00Z"
}
```

---

## State Transitions

```
ACTIVE
  ├─> PENDING_CONFIRMATION (validate)
  │     ├─> USED (confirm)
  │     │     └─> VOIDED (void within 2h)
  │     └─> ACTIVE (cancel validation)
  └─> EXPIRED (time-based)
```

---

## Redis Keys

### QR Proof Token
```
Key: sv:app:redeem:token:{token}
TTL: 30 seconds
Value: {
  "entitlement_id": "uuid",
  "user_id": "uuid",
  "offer_id": "uuid",
  "device_id": "device-123",
  "created_at": "2026-02-01T15:45:00Z"
}
```

### Daily Claim Tracking
```
Key: sv:app:claim:daily:{user_id}:{offer_id}:{date}
TTL: Until end of day
Value: "1"
```

---

## Error Codes

| Code | Error | Reason |
|------|-------|--------|
| 400 | Daily claim limit reached | User already claimed this offer today |
| 400 | Offer is not active | Offer is inactive or expired |
| 400 | Invalid or expired token | QR token expired (>30s) or doesn't exist |
| 400 | Cannot validate entitlement in {state} state | Entitlement not in ACTIVE state |
| 400 | Cannot confirm redemption for entitlement in {state} state | Entitlement not in PENDING_CONFIRMATION |
| 400 | Void window expired | More than 2 hours since redemption |
| 400 | Cannot void redemption from a different day | Redemption was yesterday or earlier |
| 401 | Invalid or expired token | JWT authentication failed |
| 404 | Entitlement not found | Invalid entitlement_id |
| 404 | Offer not found | Invalid offer_id |

---

## Savings Calculation

### Percentage Discount
```python
# Offer: 20% off
total_bill = 100.00
percentage = 20
discount = total_bill * (percentage / 100)  # 20.00
final_amount = total_bill - discount  # 80.00
```

### Buy One Get One (BOGO)
```python
# Offer: Buy 1 coffee, get 1 free
total_bill = 100.00
item_price = 50.00  # from offer.original_price
discount = item_price  # 50.00
final_amount = total_bill - discount  # 50.00
```

### Bundle
```python
# Offer: Meal bundle for AED 75 (original AED 100)
original_price = 100.00
bundle_price = 75.00
discount = original_price - bundle_price  # 25.00
final_amount = bundle_price  # 75.00
```

---

## Testing Checklist

### ✅ Happy Path
- [ ] Claim entitlement
- [ ] Generate QR token
- [ ] Validate token (PASS)
- [ ] Confirm redemption
- [ ] Verify savings calculation

### ✅ Token Expiry
- [ ] Generate QR token
- [ ] Wait 31 seconds
- [ ] Validate token (FAIL: expired)

### ✅ Token Reuse
- [ ] Validate token (PASS)
- [ ] Try to validate same token again (FAIL: already used)

### ✅ Daily Limit
- [ ] Claim entitlement (SUCCESS)
- [ ] Claim same offer again (FAIL: daily limit)

### ✅ Void Logic
- [ ] Confirm redemption
- [ ] Void within 2 hours (SUCCESS)
- [ ] Try to void after 2 hours (FAIL: window expired)

### ✅ State Machine
- [ ] Try to confirm without validation (FAIL: not pending)
- [ ] Try to void non-used entitlement (FAIL: not used)

---

## Database Queries

### Check User's Active Entitlements
```sql
SELECT * FROM entitlements
WHERE user_id = 'user-uuid'
  AND state = 'active'
  AND expires_at > NOW()
ORDER BY claimed_at DESC;
```

### Check Daily Claims
```sql
SELECT * FROM entitlements
WHERE user_id = 'user-uuid'
  AND offer_id = 'offer-uuid'
  AND DATE(claimed_at) = CURRENT_DATE
  AND state != 'voided';
```

### Get User Savings
```sql
SELECT 
  COUNT(*) as total_redemptions,
  SUM(discount_amount) as total_savings,
  SUM(final_amount) as total_spent
FROM redemptions
WHERE user_id = 'user-uuid'
  AND is_voided = FALSE;
```

### Merchant Redemption Stats
```sql
SELECT 
  DATE(redeemed_at) as date,
  COUNT(*) as redemption_count,
  SUM(total_bill_amount) as revenue,
  SUM(discount_amount) as discounts
FROM redemptions
WHERE merchant_id = 'merchant-uuid'
  AND is_voided = FALSE
GROUP BY DATE(redeemed_at)
ORDER BY date DESC;
```

---

## Monitoring Metrics

### Key Metrics to Track

1. **Token Generation Rate**
   - Tokens generated per minute
   - Alert if > 1000/min (potential abuse)

2. **Validation Success Rate**
   - PASS / (PASS + FAIL)
   - Target: > 95%

3. **Token Expiry Rate**
   - Expired tokens / Total tokens
   - Target: < 10%

4. **Void Rate**
   - Voided redemptions / Total redemptions
   - Target: < 5%

5. **Average Savings**
   - AVG(discount_amount)
   - Track per offer type

6. **Redemption Completion Time**
   - Time from claim to confirmation
   - Target: < 5 minutes

---

## Security Checklist

- [x] JWT required on all endpoints
- [x] User ID from JWT, never from request
- [x] QR tokens expire in 30s
- [x] Tokens are single-use
- [x] Daily limits enforced
- [x] State machine validates all transitions
- [x] Device binding supported
- [x] No sensitive data in error messages
- [x] RLS policies enabled
- [x] Audit logs for voids

---

## Common Issues & Solutions

### Issue: "Daily claim limit reached"
**Cause:** User already claimed this offer today  
**Solution:** Wait until tomorrow or choose different offer

### Issue: "Invalid or expired token"
**Cause:** QR token expired (>30s) or already used  
**Solution:** Generate new QR token

### Issue: "Cannot validate entitlement in used state"
**Cause:** Entitlement already redeemed  
**Solution:** This is expected behavior, entitlement can only be used once

### Issue: "Void window expired"
**Cause:** More than 2 hours since redemption  
**Solution:** Cannot void, contact support if needed

### Issue: Redis connection failed
**Cause:** Redis URL incorrect or network issue  
**Solution:** Check REDIS_URL in .env, verify Upstash connection

---

## Next Steps

1. **Run Database Migration**
   ```bash
   python migrations/phase3_setup.py
   ```

2. **Run Tests**
   ```bash
   pytest tests/test_entitlements_phase3.py -v
   ```

3. **Start Server**
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

4. **Test with Postman**
   - Import: `StudentVerse-Phase3-Redemption.postman_collection.json`
   - Set JWT token in environment
   - Run test scenarios

5. **Deploy to Staging**
   - Verify database migration
   - Test end-to-end flow
   - Monitor metrics

6. **Production Deployment**
   - Run migration on production DB
   - Deploy backend
   - Monitor for errors
   - Verify analytics tracking

---

**Quick Links:**
- [Full Documentation](docs/phase3_redemption.md)
- [Implementation README](PHASE3_README.md)
- [Test Suite](tests/test_entitlements_phase3.py)
- [Postman Collection](StudentVerse-Phase3-Redemption.postman_collection.json)
