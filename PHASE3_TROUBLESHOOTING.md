# Phase 3 Troubleshooting Guide

## Common Errors & Solutions

### Error: 500 Internal Server Error - "detail not allowed"

**Possible Causes:**

1. **Timezone/DateTime Issues** ✅ FIXED
   - The service was comparing timezone-aware and timezone-naive datetimes
   - **Solution:** Updated to handle both formats properly

2. **Missing offer fields**
   - Your offers table might not have all the expected fields
   - **Check:** Make sure your offers have `valid_from` and `valid_until`

3. **Database connection issues**
   - Supabase client not initialized properly
   - **Check:** Verify `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` in `.env`

---

## How to Debug 500 Errors

### Step 1: Check Server Logs

Look at your terminal where `uvicorn` is running. You should now see detailed error messages like:

```
ERROR: Error claiming entitlement: <actual error message>
ERROR: <full traceback>
```

### Step 2: Check Your Offer Data

Make sure your offers have the required fields:

```sql
SELECT 
    id,
    title,
    is_active,
    valid_from,
    valid_until,
    offer_type,
    discount_value,
    original_price,
    discounted_price
FROM offers
WHERE id = 'your-offer-id';
```

**Required fields:**
- ✅ `id` - UUID
- ✅ `is_active` - true
- ✅ `valid_from` - Date or DateTime
- ✅ `valid_until` - Date or DateTime
- ✅ `offer_type` - 'percentage', 'bogo', or 'bundle'

**Optional fields:**
- `time_valid_from` - Time of day (e.g., '09:00:00')
- `time_valid_until` - Time of day (e.g., '17:00:00')
- `valid_days_of_week` - Array of integers [0-6]
- `max_total_claims` - Integer
- `total_claims` - Integer (defaults to 0)

### Step 3: Test with Simple Offer

Try with a minimal offer first:

```sql
INSERT INTO offers (
    id,
    merchant_id,
    category_id,
    title,
    description,
    offer_type,
    discount_value,
    is_active,
    valid_from,
    valid_until,
    max_claims_per_user,
    total_claims,
    max_total_claims
) VALUES (
    'test-offer-simple',
    'your-merchant-id',
    'your-category-id',
    'Test Offer - 10% Off',
    'Simple test offer',
    'percentage',
    '10%',
    true,
    NOW(),
    NOW() + INTERVAL '7 days',
    1,
    0,
    100
);
```

Then claim it:

```json
{
  "offer_id": "test-offer-simple",
  "device_id": "test-device"
}
```

---

## Error Messages & Solutions

### "Offer not found"

**Cause:** The offer_id doesn't exist in the database

**Solution:**
```sql
-- Check if offer exists
SELECT * FROM offers WHERE id = 'your-offer-id';

-- If not, insert a test offer (see above)
```

---

### "Offer is not active"

**Cause:** `is_active` is false

**Solution:**
```sql
UPDATE offers 
SET is_active = true 
WHERE id = 'your-offer-id';
```

---

### "Offer is not currently valid"

**Cause:** Current date is outside `valid_from` and `valid_until` range

**Solution:**
```sql
-- Check offer validity dates
SELECT valid_from, valid_until FROM offers WHERE id = 'your-offer-id';

-- Update to be valid now
UPDATE offers 
SET 
    valid_from = NOW(),
    valid_until = NOW() + INTERVAL '30 days'
WHERE id = 'your-offer-id';
```

---

### "Daily claim limit reached for this offer"

**Cause:** You already claimed this offer today

**Solutions:**

**Option 1:** Wait until tomorrow

**Option 2:** Claim a different offer

**Option 3:** Clear Redis cache (dev only):
```python
# In Python console
from app.core.redis import redis_manager
redis_manager.connect()
redis_manager.delete(f"sv:app:claim:daily:{user_id}:{offer_id}:{today}")
```

**Option 4:** Delete the entitlement from database:
```sql
DELETE FROM entitlements 
WHERE user_id = 'your-user-id' 
  AND offer_id = 'your-offer-id'
  AND DATE(claimed_at) = CURRENT_DATE;
```

---

### "Invalid offer date format"

**Cause:** `valid_from` or `valid_until` is not in ISO format

**Solution:**
```sql
-- Check current format
SELECT valid_from, valid_until FROM offers WHERE id = 'your-offer-id';

-- Update to proper ISO format
UPDATE offers 
SET 
    valid_from = '2026-02-05T00:00:00',
    valid_until = '2026-03-05T23:59:59'
WHERE id = 'your-offer-id';
```

---

### "Unauthorized" or "Invalid token"

**Cause:** JWT token is missing or invalid

**Solutions:**

1. **Get a new JWT token:**
   - Use Phase 1 auth endpoints to login
   - Copy the JWT token from response

2. **Check Authorization header:**
   ```
   Authorization: Bearer YOUR_JWT_TOKEN_HERE
   ```
   - Make sure there's a space after "Bearer"
   - No quotes around the token

3. **Verify token in Postman:**
   - Go to Authorization tab
   - Type: Bearer Token
   - Token: Paste your JWT

---

### "Failed to create entitlement"

**Cause:** Database insert failed

**Possible reasons:**

1. **Foreign key constraint:**
   - `user_id` doesn't exist in `auth.users`
   - `offer_id` doesn't exist in `offers`

2. **Unique constraint violation:**
   - You already have an active entitlement for this offer today

**Solution:**
```sql
-- Check if user exists
SELECT id FROM auth.users WHERE id = 'your-user-id';

-- Check if offer exists
SELECT id FROM offers WHERE id = 'your-offer-id';

-- Check for existing entitlements
SELECT * FROM entitlements 
WHERE user_id = 'your-user-id' 
  AND offer_id = 'your-offer-id'
  AND DATE(claimed_at) = CURRENT_DATE;
```

---

## Testing Checklist

Before testing, verify:

- [ ] Server is running (`uvicorn app.main:app --reload --port 8000`)
- [ ] Database tables created (`entitlements`, `redemptions`)
- [ ] Sample offers inserted
- [ ] JWT token obtained and valid
- [ ] Authorization header set in Postman/API client
- [ ] Offer IDs are correct (copy from database)

---

## Quick Test

### 1. Check Server Health

```bash
curl http://localhost:8000/
```

Expected response:
```json
{
  "message": "StudentVerse API",
  "version": "1.0.0",
  "docs": "/docs",
  "health": "/health"
}
```

### 2. Check Swagger UI

Open: http://localhost:8000/docs

You should see all Phase 3 endpoints under "Entitlements" tag.

### 3. Test Claim Endpoint

**Request:**
```bash
curl -X POST http://localhost:8000/entitlements/claim \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "offer_id": "your-offer-id",
    "device_id": "test-device"
  }'
```

**Expected Success (200):**
```json
{
  "success": true,
  "message": "Entitlement claimed successfully",
  "entitlement_id": "uuid-here",
  "offer_id": "your-offer-id",
  "expires_at": "2026-02-05T23:59:59"
}
```

**Expected Error (400):**
```json
{
  "detail": "Offer not found"
}
```

---

## Database Verification

After claiming, verify in database:

```sql
-- Check entitlement was created
SELECT * FROM entitlements 
WHERE offer_id = 'your-offer-id' 
ORDER BY claimed_at DESC 
LIMIT 1;

-- Expected result:
-- id: uuid
-- user_id: your-user-id
-- offer_id: your-offer-id
-- state: 'active'
-- claimed_at: recent timestamp
-- expires_at: end of today
```

---

## Still Having Issues?

### Enable Debug Logging

Add to your `.env`:
```
LOG_LEVEL=DEBUG
```

Restart server and check logs for detailed information.

### Check Supabase Connection

```python
from app.core.database import get_supabase_client

supabase = get_supabase_client()
result = supabase.table('offers').select('*').limit(1).execute()
print(result.data)
```

### Check Redis Connection

```python
from app.core.redis import redis_manager

redis_manager.connect()
redis_manager.setex("test:key", 60, "test-value")
value = redis_manager.get("test:key")
print(value)  # Should print: test-value
```

---

## Contact Support

If you're still stuck, provide:

1. **Error message** from Postman
2. **Server logs** from terminal
3. **Offer data** from database
4. **Request body** you're sending
5. **JWT token** (first 20 characters only)

This will help diagnose the issue quickly!

---

**Last Updated:** 2026-02-05  
**Version:** 1.0.1 (with datetime fixes)
