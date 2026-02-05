# Quick Start - Phase 3 Testing

## ⚡ QUICK FIX FOR UUID ERROR

The error you're getting is because PostgreSQL expects proper UUID format.

### Step 1: Get an Existing Offer UUID

Run this in Supabase SQL Editor:

```sql
SELECT id, title, offer_type, is_active 
FROM offers 
WHERE is_active = true
LIMIT 5;
```

**Copy one of the UUIDs** (it looks like: `550e8400-e29b-41d4-a716-446655440000`)

### Step 2: Use That UUID in Postman

```json
{
  "offer_id": "paste-the-uuid-here",
  "device_id": "test-device-123"
}
```

---

## 🆕 OR Create a New Test Offer

If you want to create a fresh test offer:

### Step 1: Get Your Merchant and Category UUIDs

```sql
-- Get merchant UUID
SELECT id, name FROM merchants LIMIT 1;

-- Get category UUID
SELECT id, name FROM categories LIMIT 1;
```

Copy both UUIDs.

### Step 2: Insert Test Offer

```sql
INSERT INTO offers (
    merchant_id,
    category_id,
    title,
    description,
    offer_type,
    discount_value,
    valid_from,
    valid_until,
    max_claims_per_user,
    total_claims,
    max_total_claims,
    is_active
) VALUES (
    'paste-merchant-uuid-here',
    'paste-category-uuid-here',
    'Test Offer - 20% Off',
    'Test offer for Phase 3 testing',
    'percentage',
    '20%',
    NOW(),
    NOW() + INTERVAL '30 days',
    1,
    0,
    100,
    true
) RETURNING id, title;
```

**The `RETURNING` clause will show you the generated UUID!**

### Step 3: Copy the UUID and Test

Use the returned UUID in your Postman request:

```json
{
  "offer_id": "the-uuid-from-step-2",
  "device_id": "test-device-123"
}
```

---

## ✅ Expected Success Response

```json
{
  "success": true,
  "message": "Entitlement claimed successfully",
  "entitlement_id": "generated-uuid",
  "offer_id": "your-offer-uuid",
  "expires_at": "2026-02-05T23:59:59"
}
```

---

## 🚨 Common Errors

### "invalid input syntax for type uuid"
- **Cause:** You're using a string like `"offer-percentage-001"` instead of a proper UUID
- **Fix:** Use a real UUID from your database (see Step 1 above)

### "Offer not found"
- **Cause:** The UUID doesn't exist in your offers table
- **Fix:** Run `SELECT * FROM offers WHERE id = 'your-uuid';` to verify

### "Offer is not active"
- **Cause:** `is_active` is false
- **Fix:** `UPDATE offers SET is_active = true WHERE id = 'your-uuid';`

---

## 📋 Full Testing Sequence

Once you successfully claim an entitlement:

1. ✅ **Claim** → You're here
2. **Generate QR** → `POST /entitlements/{id}/proof`
3. **Validate** → `POST /entitlements/validate`
4. **Confirm** → `POST /entitlements/confirm`
5. **Get Entitlements** → `GET /entitlements/my`
6. **Get Savings** → `GET /entitlements/savings`

See `PHASE3_TESTING_GUIDE.md` for complete details on each step.

---

**TL;DR:** Use a real UUID from your database, not a string like "offer-percentage-001"!
