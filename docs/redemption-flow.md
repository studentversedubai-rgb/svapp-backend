# Phase 3: QR-Based Redemption System

## Overview

Phase 3 implements a secure, fraud-resistant QR-based redemption system with merchant amount capture and analytics. This system enables students to redeem offers via QR codes scanned by merchants, with comprehensive tracking and void capabilities.

---

## Architecture

### Components

1. **Entitlements Module** (`app/modules/entitlements/`)
   - Core business logic for redemption lifecycle
   - State machine for state transitions
   - QR proof token generation
   - Amount capture and savings calculation
   - Void logic

2. **Database Tables**
   - `entitlements`: Tracks claimed offers
   - `redemptions`: Records completed redemptions
   - `analytics_events`: Event tracking

3. **Redis Cache**
   - QR proof tokens (30s TTL)
   - Daily usage tracking
   - Rate limiting

---

## Entitlement Lifecycle

### States

```
ACTIVE (claimed and ready)
    ↓
PENDING_CONFIRMATION (QR validated, awaiting merchant confirmation)
    ↓
USED (successfully redeemed)
    ↓
VOIDED (reversed within 2 hours) [Terminal]

Any state → EXPIRED (time-based expiry) [Terminal]
```

### State Transitions

- **ACTIVE → PENDING_CONFIRMATION**: QR token validated by merchant
- **PENDING_CONFIRMATION → USED**: Merchant confirms with amount
- **PENDING_CONFIRMATION → ACTIVE**: Validation cancelled
- **USED → VOIDED**: Void within 2-hour window
- **Any → EXPIRED**: Automatic expiry at end of day

---

## API Endpoints

### 1. Claim Entitlement

**Endpoint:** `POST /entitlements/claim`

**Authentication:** Required (JWT)

**Request:**
```json
{
  "offer_id": "uuid",
  "device_id": "optional-device-identifier"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Entitlement claimed successfully",
  "entitlement_id": "uuid",
  "offer_id": "uuid",
  "expires_at": "2026-02-01T23:59:59Z"
}
```

**Business Rules:**
- One entitlement per user per offer per day
- Offer must be active and valid
- Entitlement expires at end of day
- Device binding for fraud prevention

---

### 2. Generate QR Proof Token

**Endpoint:** `POST /entitlements/{entitlement_id}/proof`

**Authentication:** Required (JWT)

**Response:**
```json
{
  "success": true,
  "proof_token": "secure-random-token",
  "expires_at": "2026-02-01T15:45:30Z",
  "ttl_seconds": 30
}
```

**Details:**
- Token TTL: 30 seconds
- Stored in Redis: `sv:app:redeem:token:{token}`
- Single-use token
- Frontend renders QR code from token

**Token Data (Redis):**
```json
{
  "entitlement_id": "uuid",
  "user_id": "uuid",
  "offer_id": "uuid",
  "device_id": "device-123",
  "created_at": "2026-02-01T15:45:00Z"
}
```

---

### 3. Validate Proof Token (Merchant)

**Endpoint:** `POST /entitlements/validate`

**Authentication:** Required (JWT)

**Request:**
```json
{
  "proof_token": "token-from-qr-scan"
}
```

**Response (Success):**
```json
{
  "success": true,
  "status": "PASS",
  "entitlement_id": "uuid",
  "offer_title": "20% Off All Items",
  "offer_type": "percentage",
  "discount_value": "20%",
  "merchant_name": "Coffee Shop",
  "student_name": "John Doe"
}
```

**Response (Failure):**
```json
{
  "success": false,
  "status": "FAIL",
  "reason": "Invalid or expired token"
}
```

**Validation Checks:**
- Token exists in Redis
- Entitlement is ACTIVE
- Not already used
- Device binding (if applicable)
- Time window valid

**Side Effects:**
- Marks entitlement as PENDING_CONFIRMATION

---

### 4. Confirm Redemption (Merchant)

**Endpoint:** `POST /entitlements/confirm`

**Authentication:** Required (JWT)

**Request:**
```json
{
  "entitlement_id": "uuid",
  "total_bill_amount": 100.00,
  "discounted_amount": 80.00  // Optional
}
```

**Response:**
```json
{
  "success": true,
  "message": "Redemption confirmed successfully",
  "redemption_id": "uuid",
  "entitlement_id": "uuid",
  "total_bill": 100.00,
  "discount_amount": 20.00,
  "final_amount": 80.00,
  "savings": 20.00,
  "redeemed_at": "2026-02-01T15:46:00Z"
}
```

**Savings Calculation:**

1. **Percentage Discount:**
   ```
   discount = total_bill * (percentage / 100)
   final = total_bill - discount
   ```

2. **Buy One Get One (BOGO):**
   ```
   discount = item_price (from offer.original_price)
   final = total_bill - discount
   ```

3. **Bundle:**
   ```
   discount = original_price - bundle_price
   final = bundle_price
   ```

**Side Effects:**
- Creates redemption record
- Marks entitlement as USED
- Deletes Redis token
- Logs analytics event
- Sends notification to student

---

### 5. Void Redemption

**Endpoint:** `POST /entitlements/void`

**Authentication:** Required (JWT)

**Request:**
```json
{
  "entitlement_id": "uuid",
  "reason": "Customer returned item"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Redemption voided successfully",
  "entitlement_id": "uuid",
  "voided_at": "2026-02-01T16:00:00Z"
}
```

**Business Rules:**
- Only USED entitlements can be voided
- Must be within 2 hours of redemption
- Same day only
- Requires reason (audit log)

**Side Effects:**
- Marks redemption as voided
- Marks entitlement as VOIDED
- Logs analytics event

---

### 6. Get User Entitlements

**Endpoint:** `GET /entitlements/my?state=active`

**Authentication:** Required (JWT)

**Query Parameters:**
- `state` (optional): Filter by state (active, used, voided, expired)

**Response:**
```json
[
  {
    "id": "uuid",
    "offer_title": "20% Off All Items",
    "merchant_name": "Coffee Shop",
    "state": "active",
    "claimed_at": "2026-02-01T10:00:00Z",
    "expires_at": "2026-02-01T23:59:59Z"
  }
]
```

---

### 7. Get User Savings Summary

**Endpoint:** `GET /entitlements/savings`

**Authentication:** Required (JWT)

**Response:**
```json
{
  "total_redemptions": 15,
  "total_savings": 450.00,
  "total_spent": 1200.00
}
```

---

## Security & Fraud Prevention

### 1. Short-Lived Tokens
- QR proof tokens expire in 30 seconds
- Prevents token sharing and replay attacks

### 2. Single-Use Tokens
- Token deleted from Redis after validation
- Cannot be reused

### 3. Daily Usage Enforcement
- One entitlement per user per offer per day
- Tracked in Redis and database
- Unique index prevents duplicates

### 4. Device Binding
- Optional device_id stored with entitlement
- Can be used for additional validation

### 5. State Machine Enforcement
- All transitions validated
- Invalid transitions rejected

### 6. JWT Authentication
- All endpoints require valid JWT
- User ID derived from token (never from request body)

### 7. Rate Limiting
- Redis-based rate limiting
- IP-based and user-based limits

---

## Analytics & Reporting

### Events Tracked

1. **offer_claim**
   - User claims an offer
   - Data: user_id, offer_id, entitlement_id

2. **redemption_confirmed**
   - Redemption completed
   - Data: user_id, offer_id, merchant_id, savings

3. **redemption_voided**
   - Redemption voided
   - Data: user_id, entitlement_id, reason

### Analytics Queries

**User Savings:**
```sql
SELECT 
  user_id,
  COUNT(*) as total_redemptions,
  SUM(discount_amount) as total_savings
FROM redemptions
WHERE is_voided = FALSE
GROUP BY user_id;
```

**Merchant ROI:**
```sql
SELECT 
  merchant_id,
  COUNT(*) as redemption_count,
  SUM(total_bill_amount) as sv_attributed_revenue,
  SUM(discount_amount) as total_discounts
FROM redemptions
WHERE is_voided = FALSE
GROUP BY merchant_id;
```

**Offer Performance:**
```sql
SELECT 
  offer_id,
  COUNT(*) as redemption_count,
  AVG(discount_amount) as avg_savings
FROM redemptions
WHERE is_voided = FALSE
GROUP BY offer_id;
```

---

## Database Schema

### Entitlements Table

```sql
CREATE TABLE entitlements (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL,
  offer_id UUID NOT NULL,
  device_id VARCHAR,
  state VARCHAR NOT NULL,
  claimed_at TIMESTAMP WITH TIME ZONE,
  expires_at TIMESTAMP WITH TIME ZONE,
  used_at TIMESTAMP WITH TIME ZONE,
  voided_at TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE,
  updated_at TIMESTAMP WITH TIME ZONE
);

-- Unique constraint for daily usage
CREATE UNIQUE INDEX idx_entitlements_user_offer_day 
ON entitlements(user_id, offer_id, DATE(claimed_at))
WHERE state != 'voided';
```

### Redemptions Table

```sql
CREATE TABLE redemptions (
  id UUID PRIMARY KEY,
  entitlement_id UUID NOT NULL,
  merchant_id UUID NOT NULL,
  offer_id UUID NOT NULL,
  user_id UUID NOT NULL,
  total_bill_amount DECIMAL(10, 2),
  discount_amount DECIMAL(10, 2),
  final_amount DECIMAL(10, 2),
  offer_type VARCHAR,
  redeemed_at TIMESTAMP WITH TIME ZONE,
  is_voided BOOLEAN,
  voided_at TIMESTAMP WITH TIME ZONE,
  void_reason TEXT,
  created_at TIMESTAMP WITH TIME ZONE,
  updated_at TIMESTAMP WITH TIME ZONE
);
```

---

## Redis Keys

### QR Proof Tokens
```
Key: sv:app:redeem:token:{token}
TTL: 30 seconds
Value: JSON with entitlement_id, user_id, offer_id, device_id
```

### Daily Usage Tracking
```
Key: sv:app:claim:daily:{user_id}:{offer_id}:{date}
TTL: Until end of day
Value: "1"
```

---

## Testing

### Test Coverage

1. **QR Token Expiry**
   - Token expires after 30 seconds
   - Validation fails for expired tokens

2. **Token Reuse Rejection**
   - Token cannot be used twice
   - Second validation fails

3. **Daily Usage Enforcement**
   - Second claim on same day fails
   - Voided entitlements don't count

4. **Savings Computation**
   - Percentage: 20% of 100 = 20
   - BOGO: Item price = discount
   - Bundle: Original - Bundle = discount

5. **Void Logic**
   - Void succeeds within 2 hours
   - Void fails after 2 hours
   - Void fails for different day

6. **State Machine**
   - Valid transitions succeed
   - Invalid transitions fail
   - Terminal states cannot transition

### Run Tests

```bash
pytest tests/test_entitlements_phase3.py -v
```

---

## Deployment Checklist

- [ ] Run database migration (`migrations/phase3_setup.py`)
- [ ] Verify Redis connection
- [ ] Test QR token generation
- [ ] Test validation flow
- [ ] Test confirmation flow
- [ ] Test void logic
- [ ] Verify analytics tracking
- [ ] Set up monitoring for:
  - Token expiry rates
  - Validation success rates
  - Void rates
  - Average savings per redemption

---

## Future Enhancements

1. **Merchant Dashboard**
   - Real-time redemption stats
   - Revenue analytics
   - Fraud detection alerts

2. **Student Notifications**
   - Push notification on redemption
   - Savings milestones
   - Offer recommendations

3. **Advanced Fraud Detection**
   - Velocity checks
   - Anomaly detection
   - Merchant verification

4. **Offline Support**
   - OTP fallback for QR codes
   - Offline validation queue

---

## Support

For issues or questions:
- Check logs in `/var/log/studentverse/`
- Review analytics in Supabase dashboard
- Contact backend team

---

**Last Updated:** 2026-02-01  
**Version:** 1.0.0  
**Status:** Production Ready
