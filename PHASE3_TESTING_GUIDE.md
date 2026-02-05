# Phase 3 Testing Guide

## Complete Database Setup & Testing Instructions

This guide provides **everything you need** to test Phase 3, including:
- All required database tables
- Sample data to insert
- API endpoints to test
- Step-by-step testing flow

---

## 📋 Required Database Tables

You already have:
- ✅ `categories`
- ✅ `merchants`
- ✅ `offers`

You need to create for Phase 3:
- ⬜ `entitlements`
- ⬜ `redemptions`
- ⬜ `analytics_events` (optional but recommended)

---

## 🗄️ Database Setup

### Step 1: Create Entitlements Table

```sql
-- Create entitlements table
CREATE TABLE IF NOT EXISTS entitlements (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    offer_id UUID NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
    device_id VARCHAR,
    
    state VARCHAR NOT NULL DEFAULT 'active',
    
    claimed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE,
    voided_at TIMESTAMP WITH TIME ZONE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT valid_state CHECK (state IN ('active', 'pending_confirmation', 'used', 'voided', 'expired'))
);

-- Create indexes
CREATE INDEX idx_entitlements_user_id ON entitlements(user_id);
CREATE INDEX idx_entitlements_offer_id ON entitlements(offer_id);
CREATE INDEX idx_entitlements_state ON entitlements(state);
CREATE INDEX idx_entitlements_claimed_at ON entitlements(claimed_at);
CREATE INDEX idx_entitlements_expires_at ON entitlements(expires_at);

-- Unique constraint for daily usage (one claim per user per offer per day)
CREATE UNIQUE INDEX idx_entitlements_user_offer_day 
ON entitlements(user_id, offer_id, DATE(claimed_at))
WHERE state != 'voided';
```


### Step 2: Create Redemptions Table

```sql
-- Create redemptions table
CREATE TABLE IF NOT EXISTS redemptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entitlement_id UUID NOT NULL REFERENCES entitlements(id) ON DELETE CASCADE,
    
    merchant_id UUID NOT NULL REFERENCES merchants(id),
    offer_id UUID NOT NULL REFERENCES offers(id),
    user_id UUID NOT NULL,
    
    total_bill_amount DECIMAL(10, 2) NOT NULL,
    discount_amount DECIMAL(10, 2) NOT NULL,
    final_amount DECIMAL(10, 2) NOT NULL,
    
    offer_type VARCHAR NOT NULL,
    
    redeemed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    is_voided BOOLEAN DEFAULT FALSE,
    voided_at TIMESTAMP WITH TIME ZONE,
    void_reason TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes
CREATE INDEX idx_redemptions_entitlement_id ON redemptions(entitlement_id);
CREATE INDEX idx_redemptions_merchant_id ON redemptions(merchant_id);
CREATE INDEX idx_redemptions_offer_id ON redemptions(offer_id);
CREATE INDEX idx_redemptions_user_id ON redemptions(user_id);
CREATE INDEX idx_redemptions_redeemed_at ON redemptions(redeemed_at);
CREATE INDEX idx_redemptions_is_voided ON redemptions(is_voided);
```

### Step 3: Create Analytics Events Table (Optional)

```sql
-- Create analytics_events table
CREATE TABLE IF NOT EXISTS analytics_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type VARCHAR NOT NULL,
    event_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes
CREATE INDEX idx_analytics_events_type ON analytics_events(event_type);
CREATE INDEX idx_analytics_events_created_at ON analytics_events(created_at);
```

---

## 📊 Sample Data to Insert

### 1. Ensure You Have Sample Merchant

```sql
-- Check if you have a merchant
SELECT * FROM merchants LIMIT 1;

-- If not, insert one
INSERT INTO merchants (id, name, description, logo_url, latitude, longitude, address, is_active)
VALUES (
    'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
    'Coffee Paradise',
    'Best coffee in Dubai',
    'https://example.com/logo.png',
    25.2048,
    55.2708,
    'Dubai Mall, Dubai, UAE',
    true
);
```

### 2. Ensure You Have Sample Category

```sql
-- Check if you have a category
SELECT * FROM categories LIMIT 1;

-- If not, insert one
INSERT INTO categories (id, name, slug, description, is_active)
VALUES (
    'cat-food-beverage-001',
    'Food & Beverage',
    'food-beverage',
    'Restaurants, cafes, and food outlets',
    true
);
```

### 3. Get Existing Offers OR Insert New Ones

**IMPORTANT:** PostgreSQL requires proper UUID format for offer IDs!

#### Option A: Use Existing Offers (RECOMMENDED)

```sql
-- Check what offers you already have
SELECT id, title, offer_type, is_active, valid_from, valid_until
FROM offers 
WHERE is_active = true
ORDER BY created_at DESC
LIMIT 5;
```

**Copy one of the UUIDs and use it in your API requests!**

#### Option B: Insert New Test Offers

**First, get your merchant and category UUIDs:**

```sql
-- Get merchant UUID
SELECT id, name FROM merchants LIMIT 1;

-- Get category UUID
SELECT id, name FROM categories LIMIT 1;
```

**Then insert offers (UUIDs will be auto-generated):**

```sql
-- Offer 1: Percentage Discount (20% off)
INSERT INTO offers (
    merchant_id,
    category_id,
    title,
    description,
    terms_conditions,
    offer_type,
    discount_value,
    image_url,
    valid_from,
    valid_until,
    max_claims_per_user,
    total_claims,
    max_total_claims,
    true,
    true
);

-- Offer 2: Buy One Get One (BOGO)
INSERT INTO offers (
    id,
    merchant_id,
    category_id,
    title,
    description,
    terms_conditions,
    offer_type,
    discount_value,
    original_price,
    discounted_price,
    image_url,
    valid_from,
    valid_until,
    max_claims_per_user,
    total_claims,
    max_total_claims,
    is_active,
    is_featured
) VALUES (
    'offer-bogo-001',
    'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
    'cat-food-beverage-001',
    'Buy 1 Get 1 Free - Cappuccino',
    'Buy one cappuccino, get one free',
    'Valid on regular size cappuccino only.',
    'bogo',
    'Buy 1 Get 1',
    50.00,  -- Price of one cappuccino
    NULL,
    'https://example.com/bogo-offer.jpg',
    NOW(),
    NOW() + INTERVAL '30 days',
    1,
    0,
    500,
    true,
    false
);

-- Offer 3: Bundle Deal
INSERT INTO offers (
    id,
    merchant_id,
    category_id,
    title,
    description,
    terms_conditions,
    offer_type,
    discount_value,
    original_price,
    discounted_price,
    image_url,
    valid_from,
    valid_until,
    max_claims_per_user,
    total_claims,
    max_total_claims,
    is_active,
    is_featured
) VALUES (
    'offer-bundle-001',
    'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
    'cat-food-beverage-001',
    'Breakfast Bundle - AED 75',
    'Coffee + Sandwich + Pastry for AED 75 (Regular AED 100)',
    'Available until 11 AM daily.',
    'bundle',
    'Bundle Deal',
    100.00,  -- Original price
    75.00,   -- Bundle price
    'https://example.com/bundle-offer.jpg',
    NOW(),
    NOW() + INTERVAL '30 days',
    1,
    0,
    300,
    true,
    true
);
```

---

## 🧪 Testing Flow

### Prerequisites

1. **Get JWT Token**
   - You need to authenticate first using Phase 1 auth endpoints
   - Get a valid JWT token
   - Use this token in all Phase 3 requests

2. **Get User ID**
   - Your JWT token contains the user_id
   - You'll need this for manual database queries

---

## 🔄 Complete Testing Sequence

### Test 1: Claim Entitlement (Percentage Offer)

**Endpoint:** `POST /entitlements/claim`

**Request:**
```json
{
  "offer_id": "offer-percentage-001",
  "device_id": "test-device-123"
}
```

**Headers:**
```
Authorization: Bearer YOUR_JWT_TOKEN
Content-Type: application/json
```

**Expected Response (200 OK):**
```json
{
  "success": true,
  "message": "Entitlement claimed successfully",
  "entitlement_id": "ent-uuid-generated",
  "offer_id": "offer-percentage-001",
  "expires_at": "2026-02-03T23:59:59Z"
}
```

**Verify in Database:**
```sql
SELECT * FROM entitlements 
WHERE offer_id = 'offer-percentage-001' 
ORDER BY claimed_at DESC LIMIT 1;
```

---

### Test 2: Generate QR Proof Token

**Endpoint:** `POST /entitlements/{entitlement_id}/proof`

**Replace `{entitlement_id}` with the ID from Test 1**

**Headers:**
```
Authorization: Bearer YOUR_JWT_TOKEN
```

**Expected Response (200 OK):**
```json
{
  "success": true,
  "proof_token": "long-random-token-string",
  "expires_at": "2026-02-03T22:48:00Z",
  "ttl_seconds": 30
}
```

**⚠️ IMPORTANT:** Copy the `proof_token` - you have 30 seconds to use it!

**Verify in Redis:**
The token is stored in Redis with key: `sv:app:redeem:token:{proof_token}`

---

### Test 3: Validate Proof Token (Merchant Scans QR)

**Endpoint:** `POST /entitlements/validate`

**Request:**
```json
{
  "proof_token": "paste-token-from-test-2"
}
```

**Headers:**
```
Authorization: Bearer YOUR_JWT_TOKEN
Content-Type: application/json
```

**Expected Response (200 OK - PASS):**
```json
{
  "success": true,
  "status": "PASS",
  "entitlement_id": "ent-uuid",
  "offer_title": "20% Off All Coffee",
  "offer_type": "percentage",
  "discount_value": "20%",
  "merchant_name": "Coffee Paradise",
  "student_name": "Your Name"
}
```

**Verify in Database:**
```sql
SELECT * FROM entitlements 
WHERE id = 'your-entitlement-id';
-- State should be 'pending_confirmation'
```

---

### Test 4: Confirm Redemption with Amount

**Endpoint:** `POST /entitlements/confirm`

**Request:**
```json
{
  "entitlement_id": "paste-entitlement-id",
  "total_bill_amount": 100.00,
  "discounted_amount": 80.00
}
```

**Headers:**
```
Authorization: Bearer YOUR_JWT_TOKEN
Content-Type: application/json
```

**Expected Response (200 OK):**
```json
{
  "success": true,
  "message": "Redemption confirmed successfully",
  "redemption_id": "red-uuid-generated",
  "entitlement_id": "ent-uuid",
  "total_bill": 100.00,
  "discount_amount": 20.00,
  "final_amount": 80.00,
  "savings": 20.00,
  "redeemed_at": "2026-02-03T22:48:30Z"
}
```

**Verify in Database:**
```sql
-- Check entitlement is marked as USED
SELECT * FROM entitlements WHERE id = 'your-entitlement-id';
-- State should be 'used', used_at should be set

-- Check redemption record created
SELECT * FROM redemptions WHERE entitlement_id = 'your-entitlement-id';
```

---

### Test 5: Get User Entitlements

**Endpoint:** `GET /entitlements/my`

**Headers:**
```
Authorization: Bearer YOUR_JWT_TOKEN
```

**Expected Response (200 OK):**
```json
[
  {
    "id": "ent-uuid",
    "offer_title": "20% Off All Coffee",
    "merchant_name": "Coffee Paradise",
    "state": "used",
    "claimed_at": "2026-02-03T22:47:00Z",
    "expires_at": "2026-02-03T23:59:59Z"
  }
]
```

---

### Test 6: Get User Savings Summary

**Endpoint:** `GET /entitlements/savings`

**Headers:**
```
Authorization: Bearer YOUR_JWT_TOKEN
```

**Expected Response (200 OK):**
```json
{
  "total_redemptions": 1,
  "total_savings": 20.00,
  "total_spent": 80.00
}
```

---

### Test 7: Void Redemption (Within 2 Hours)

**Endpoint:** `POST /entitlements/void`

**Request:**
```json
{
  "entitlement_id": "paste-entitlement-id",
  "reason": "Customer returned the item"
}
```

**Headers:**
```
Authorization: Bearer YOUR_JWT_TOKEN
Content-Type: application/json
```

**Expected Response (200 OK):**
```json
{
  "success": true,
  "message": "Redemption voided successfully",
  "entitlement_id": "ent-uuid",
  "voided_at": "2026-02-03T23:00:00Z"
}
```

**Verify in Database:**
```sql
-- Check entitlement is voided
SELECT * FROM entitlements WHERE id = 'your-entitlement-id';
-- State should be 'voided', voided_at should be set

-- Check redemption is marked as voided
SELECT * FROM redemptions WHERE entitlement_id = 'your-entitlement-id';
-- is_voided should be true, void_reason should be set
```

---

## 🧪 Additional Test Scenarios

### Test 8: Daily Limit Enforcement

**Try to claim the same offer twice in one day:**

1. Claim offer → Success
2. Claim same offer again → **Should FAIL with 400 Bad Request**

**Expected Error:**
```json
{
  "detail": "Daily claim limit reached for this offer"
}
```

---

### Test 9: Token Expiry

1. Generate QR token
2. **Wait 31 seconds**
3. Try to validate token → **Should FAIL**

**Expected Response:**
```json
{
  "success": false,
  "status": "FAIL",
  "reason": "Invalid or expired token"
}
```

---

### Test 10: Token Reuse

1. Validate token → PASS
2. Try to validate same token again → **Should FAIL**

**Expected Response:**
```json
{
  "success": false,
  "status": "FAIL",
  "reason": "Cannot validate entitlement in used state"
}
```

---

### Test 11: Void Window Expired

**To test this, you need a redemption older than 2 hours:**

**Manual Setup:**
```sql
-- Update a redemption to be 3 hours old
UPDATE redemptions 
SET redeemed_at = NOW() - INTERVAL '3 hours'
WHERE id = 'your-redemption-id';

UPDATE entitlements
SET used_at = NOW() - INTERVAL '3 hours'
WHERE id = 'your-entitlement-id';
```

**Then try to void:**
```json
{
  "entitlement_id": "old-entitlement-id",
  "reason": "Testing void window"
}
```

**Expected Error:**
```json
{
  "detail": "Void window expired. Must void within 2 hours of redemption"
}
```

---

### Test 12: BOGO Offer

**Repeat Tests 1-4 with BOGO offer:**

**Claim:**
```json
{
  "offer_id": "offer-bogo-001",
  "device_id": "test-device-123"
}
```

**Confirm with amount:**
```json
{
  "entitlement_id": "ent-uuid",
  "total_bill_amount": 100.00
}
```

**Expected savings:** 50.00 (item price)

---

### Test 13: Bundle Offer

**Repeat Tests 1-4 with Bundle offer:**

**Claim:**
```json
{
  "offer_id": "offer-bundle-001",
  "device_id": "test-device-123"
}
```

**Confirm with amount:**
```json
{
  "entitlement_id": "ent-uuid",
  "total_bill_amount": 100.00
}
```

**Expected savings:** 25.00 (100 - 75)

---

## 📋 Testing Checklist

### Database Setup
- [ ] Created `entitlements` table
- [ ] Created `redemptions` table
- [ ] Created `analytics_events` table
- [ ] Inserted sample merchant
- [ ] Inserted sample category
- [ ] Inserted 3 sample offers (percentage, BOGO, bundle)

### Happy Path Tests
- [ ] Test 1: Claim entitlement (percentage)
- [ ] Test 2: Generate QR token
- [ ] Test 3: Validate token
- [ ] Test 4: Confirm redemption
- [ ] Test 5: Get user entitlements
- [ ] Test 6: Get savings summary
- [ ] Test 7: Void redemption

### Edge Case Tests
- [ ] Test 8: Daily limit enforcement
- [ ] Test 9: Token expiry (30s)
- [ ] Test 10: Token reuse rejection
- [ ] Test 11: Void window expired
- [ ] Test 12: BOGO offer flow
- [ ] Test 13: Bundle offer flow

### Verification
- [ ] Check entitlements table after each claim
- [ ] Check redemptions table after confirmation
- [ ] Verify savings calculations are correct
- [ ] Verify state transitions are correct

---

## 🔍 Useful Database Queries

### Check All Entitlements
```sql
SELECT 
    e.id,
    e.state,
    o.title as offer_title,
    e.claimed_at,
    e.expires_at,
    e.used_at
FROM entitlements e
JOIN offers o ON e.offer_id = o.id
ORDER BY e.claimed_at DESC;
```

### Check All Redemptions
```sql
SELECT 
    r.id,
    o.title as offer_title,
    r.total_bill_amount,
    r.discount_amount,
    r.final_amount,
    r.is_voided,
    r.redeemed_at
FROM redemptions r
JOIN offers o ON r.offer_id = o.id
ORDER BY r.redeemed_at DESC;
```

### Check User's Total Savings
```sql
SELECT 
    COUNT(*) as total_redemptions,
    SUM(discount_amount) as total_savings,
    SUM(final_amount) as total_spent
FROM redemptions
WHERE user_id = 'your-user-id'
  AND is_voided = FALSE;
```

### Check Daily Claims for User
```sql
SELECT 
    e.*,
    o.title
FROM entitlements e
JOIN offers o ON e.offer_id = o.id
WHERE e.user_id = 'your-user-id'
  AND DATE(e.claimed_at) = CURRENT_DATE
  AND e.state != 'voided';
```

---

## 🚨 Common Issues & Solutions

### Issue: "Offer not found"
**Solution:** Make sure you inserted the sample offers and use the correct `offer_id`

### Issue: "Daily claim limit reached"
**Solution:** Either wait until tomorrow or use a different offer_id

### Issue: "Invalid or expired token"
**Solution:** Generate a new QR token (they expire in 30 seconds)

### Issue: "Cannot validate entitlement in used state"
**Solution:** You already used this entitlement. Claim a new one.

### Issue: "Unauthorized"
**Solution:** Make sure you're sending the JWT token in the Authorization header

---

## 📱 Postman Collection

Import the Postman collection for easier testing:
- File: `StudentVerse-Phase3-Redemption.postman_collection.json`
- Set environment variables:
  - `base_url`: http://localhost:8000
  - `jwt_token`: Your JWT token
  - `offer_id`: One of your offer IDs

---

## ✅ Success Criteria

After completing all tests, you should have:
- ✅ At least 3 entitlements in different states
- ✅ At least 1 redemption record
- ✅ Correct savings calculations for each offer type
- ✅ Verified daily limit enforcement
- ✅ Verified token expiry and reuse prevention
- ✅ Verified void logic works

---

**Ready to test?** Start with the database setup, then follow the testing sequence!

**Need help?** Check the other documentation files:
- `docs/phase3_redemption.md` - Complete API reference
- `PHASE3_QUICK_REFERENCE.md` - Quick reference guide
- `PHASE3_DEPLOYMENT_CHECKLIST.md` - Deployment checklist
