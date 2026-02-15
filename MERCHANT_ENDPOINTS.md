# Merchant Validation Endpoints - Implementation Summary

**Date**: February 15, 2026  
**Module**: `app/modules/merchant/`  
**Prefix**: `/merchant`

---

## What Was Added

### New Module: Merchant Validation
Created a complete merchant-side validation system for QR-based redemptions. This module operates **independently** from student-facing endpoints and does **NOT require JWT authentication**.

### Files Created
1. **`app/modules/merchant/__init__.py`** - Module initialization
2. **`app/modules/merchant/schemas.py`** - Request/response models
3. **`app/modules/merchant/service.py`** - Business logic
4. **`app/modules/merchant/router.py`** - API endpoints

### Integration
- **`app/main.py`** - Registered merchant router under `/merchant` prefix

---

## Endpoints Created

### 1. POST /merchant/validate
**Purpose**: Validate student's QR proof token

**Authentication**: None required (public endpoint)

**Request**:
```json
{
  "proof_token": "student-qr-token-here"
}
```

**Response (PASS)**:
```json
{
  "success": true,
  "status": "PASS",
  "entitlement_id": "uuid",
  "offer_title": "20% Off Coffee",
  "offer_type": "percentage",
  "discount_value": "20%",
  "merchant_name": "Coffee Paradise",
  "student_name": "John Doe",
  "original_price": 100.00,
  "discounted_price": 75.00
}
```

**Response (FAIL)**:
```json
{
  "success": false,
  "status": "FAIL",
  "reason": "Invalid or expired token"
}
```

**Business Rules**:
- ✅ Validates token from Redis (30s TTL)
- ✅ Checks entitlement is ACTIVE
- ✅ Checks entitlement not expired
- ✅ Returns offer and student details on success
- ✅ Rate limited: 100 req/min per IP

---

### 2. POST /merchant/confirm
**Purpose**: Confirm redemption with merchant PIN and bill amount

**Authentication**: Merchant PIN required

**Request**:
```json
{
  "proof_token": "student-qr-token-here",
  "merchant_pin": "1234",
  "total_bill_amount": 100.00
}
```

**Response**:
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
  "redeemed_at": "2026-02-15T13:00:00Z"
}
```

**Business Rules**:
- ✅ Validates proof token
- ✅ Verifies merchant PIN (SHA256 hashed)
- ✅ Calculates discount server-side based on offer type:
  - **Percentage**: `(bill * percentage) / 100`
  - **BOGO**: `original_price` (item price)
  - **Bundle**: `original_price - discounted_price`
- ✅ Creates redemption record in database
- ✅ Marks entitlement as USED
- ✅ Deletes Redis token (single-use)
- ✅ Logs analytics event
- ✅ Rate limited: 60 req/min per IP

---

### 3. POST /merchant/void
**Purpose**: Void a redemption within the void window

**Authentication**: Merchant PIN required

**Request**:
```json
{
  "redemption_id": "uuid",
  "merchant_pin": "1234",
  "reason": "Customer returned item"
}
```

**Response**:
```json
{
  "success": true,
  "message": "Redemption voided successfully",
  "redemption_id": "uuid",
  "voided_at": "2026-02-15T13:30:00Z"
}
```

**Business Rules**:
- ✅ Verifies merchant PIN
- ✅ Checks void window (2 hours from redemption)
- ✅ Checks same day as redemption
- ✅ Marks redemption as voided
- ✅ Updates entitlement state to VOIDED
- ✅ Logs analytics event
- ✅ Rate limited: 60 req/min per IP

---

### 4. GET /merchant/health
**Purpose**: Health check for merchant endpoints

**Response**:
```json
{
  "status": "ok",
  "service": "merchant-validation"
}
```

---

## Security Features

### 1. Merchant PIN Authentication
- **Storage**: PINs hashed with SHA256 before storage
- **Verification**: Constant-time comparison
- **Column**: `merchants.pin_hash` (needs to be added to database)

### 2. Rate Limiting
- **Validate**: 100 requests/minute per IP
- **Confirm**: 60 requests/minute per IP
- **Void**: 60 requests/minute per IP

### 3. Server-Side Calculations
- ✅ All discount calculations performed server-side
- ✅ No client-provided amounts trusted
- ✅ Offer type determines calculation method

### 4. Single-Use Tokens
- ✅ QR tokens deleted after successful confirmation
- ✅ Cannot be reused
- ✅ 30-second TTL enforced

### 5. Void Window Enforcement
- ✅ 2-hour window from redemption time
- ✅ Same-day restriction
- ✅ State machine validation

---

## Database Requirements

### New Column Needed
Add `pin_hash` column to `merchants` table:

```sql
ALTER TABLE merchants 
ADD COLUMN pin_hash VARCHAR(64);

-- Example: Setting PIN "1234" for a merchant
-- SHA256 hash of "1234" = 03ac674216f3e15c761ee1a5e255f067953623c8b388b4459e13f978d7c846f4
UPDATE merchants 
SET pin_hash = '03ac674216f3e15c761ee1a5e255f067953623c8b388b4459e13f978d7c846f4'
WHERE id = 'merchant-uuid';
```

### Existing Tables Used
- ✅ `entitlements` - Read/update entitlement state
- ✅ `redemptions` - Create/update redemption records
- ✅ `offers` - Read offer details
- ✅ `merchants` - Read merchant details, verify PIN
- ✅ `users` - Read student name
- ✅ `analytics_events` - Log events

---

## Integration with Existing System

### Phase 1-4 Endpoints
- ✅ **No modifications** to existing student endpoints
- ✅ **No changes** to JWT authentication flow
- ✅ **No changes** to entitlements service (student-facing)

### Shared Resources
- ✅ Uses same Redis instance for QR tokens
- ✅ Uses same Supabase database
- ✅ Uses same analytics events table
- ✅ Uses same entitlements state machine

### Separation of Concerns
- ✅ Merchant endpoints under `/merchant/*`
- ✅ Student endpoints under `/entitlements/*`
- ✅ No JWT required for merchant endpoints
- ✅ Merchant PIN used for authorization

---

## Testing

### Manual Testing
1. **Start server**: `uvicorn app.main:app --reload --port 8000`
2. **Access Swagger**: http://localhost:8000/docs
3. **Find "Merchant Validation" section**
4. **Test endpoints** in order:
   - Validate → Confirm → Void

### Test Flow
```
1. Student claims offer → GET /entitlements/claim
2. Student generates QR → POST /entitlements/{id}/proof
3. Merchant validates QR → POST /merchant/validate
4. Merchant confirms → POST /merchant/confirm
5. (Optional) Merchant voids → POST /merchant/void
```

### Sample Test Data
```json
// Validate
{
  "proof_token": "token-from-student-qr"
}

// Confirm
{
  "proof_token": "token-from-student-qr",
  "merchant_pin": "1234",
  "total_bill_amount": 100.00
}

// Void
{
  "redemption_id": "redemption-uuid-from-confirm",
  "merchant_pin": "1234",
  "reason": "Customer returned item"
}
```

---

## Error Handling

### Common Errors

**400 Bad Request**:
- Invalid or expired token
- Entitlement not in correct state
- Invalid merchant PIN
- Void window expired
- Invalid input data

**500 Internal Server Error**:
- Database connection issues
- Redis connection issues
- Unexpected server errors

### Error Response Format
```json
{
  "detail": "Error message here"
}
```

---

## Monitoring & Analytics

### Events Logged
1. **`redemption_confirmed`** - When merchant confirms redemption
   - redemption_id
   - merchant_id
   - offer_id
   - savings amount

2. **`redemption_voided`** - When merchant voids redemption
   - redemption_id
   - void reason

### Metrics to Track
- Validation success/failure rate
- Confirmation success/failure rate
- Void rate
- Average time between validate and confirm
- PIN verification failures

---

## Production Deployment

### Pre-Deployment Checklist
- [ ] Add `pin_hash` column to merchants table
- [ ] Set merchant PINs (hashed)
- [ ] Configure rate limiting
- [ ] Test all three endpoints
- [ ] Verify analytics logging
- [ ] Test void window enforcement

### Environment Variables
No new environment variables required. Uses existing:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `REDIS_URL`

---

## Summary

✅ **3 new public endpoints** created under `/merchant`  
✅ **No JWT authentication** required (uses merchant PIN)  
✅ **Server-side discount calculations** for all offer types  
✅ **PIN security** with SHA256 hashing  
✅ **Rate limiting** on all endpoints  
✅ **Void window enforcement** (2 hours, same day)  
✅ **Analytics logging** for all operations  
✅ **Zero modifications** to Phase 1-4 code  

**Status**: Ready for testing and deployment 🚀
