# Testing Merchant Validation Endpoints - Quick Guide

## Prerequisites

Before testing, you need:
1. ✅ Server running
2. ✅ Database with merchant PIN set
3. ✅ A valid student entitlement with QR token

---

## Step 1: Add Merchant PIN to Database

Run this SQL in Supabase SQL Editor:

```sql
-- Add pin_hash column if not exists
ALTER TABLE merchants 
ADD COLUMN IF NOT EXISTS pin_hash VARCHAR(64);

-- Set PIN "1234" for your merchant
-- SHA256 hash of "1234"
UPDATE merchants 
SET pin_hash = '03ac674216f3e15c761ee1a5e255f067953623c8b388b4459e13f978d7c846f4'
WHERE id = (SELECT id FROM merchants LIMIT 1);

-- Verify it was set
SELECT id, name, pin_hash FROM merchants LIMIT 1;
```

**Note**: PIN "1234" will be used for testing. Change in production!

---

## Step 2: Start the Server

```bash
cd c:\Users\msina\OneDrive\Desktop\sv\sv-backend
uvicorn app.main:app --reload --port 8000
```

Wait for: `Application startup complete`

---

## Step 3: Get a QR Proof Token

You need a valid QR token from a student entitlement. Two options:

### Option A: Use Existing Student Flow (Recommended)

1. **Open Swagger UI**: http://localhost:8000/docs
2. **Authenticate as student**:
   - Use `/auth/send-otp` and `/auth/verify-otp`
   - Copy the JWT token
3. **Claim an offer**:
   - Click on `POST /entitlements/claim`
   - Click "Try it out"
   - Add your JWT in Authorization header
   - Request body:
     ```json
     {
       "offer_id": "your-offer-uuid",
       "device_id": "test-device"
     }
     ```
   - Execute
   - Copy the `entitlement_id` from response

4. **Generate QR token**:
   - Click on `POST /entitlements/{entitlement_id}/proof`
   - Click "Try it out"
   - Paste the `entitlement_id`
   - Execute
   - **Copy the `proof_token`** - you have 30 seconds!

### Option B: Quick Test with Manual Token (For Testing Only)

If you just want to test the merchant endpoints quickly:

```python
# Run this in Python console
import secrets
import json
from app.core.redis import redis_manager

# Connect to Redis
redis_manager.connect()

# Create a test token
proof_token = secrets.token_urlsafe(32)
token_data = {
    "entitlement_id": "your-entitlement-uuid",
    "user_id": "your-user-uuid",
    "offer_id": "your-offer-uuid",
    "device_id": "test-device",
    "created_at": "2026-02-15T13:00:00Z"
}

# Store in Redis (30s TTL)
redis_manager.setex(
    f"sv:app:redeem:token:{proof_token}",
    30,
    json.dumps(token_data)
)

print(f"Test token: {proof_token}")
```

---

## Step 4: Test Merchant Endpoints

### Test 1: Validate QR Token

**Endpoint**: `POST /merchant/validate`

**In Swagger UI**:
1. Find "Merchant Validation" section
2. Click on `POST /merchant/validate`
3. Click "Try it out"
4. Request body:
   ```json
   {
     "proof_token": "paste-your-token-here"
   }
   ```
5. Click "Execute"

**Expected Response (PASS)**:
```json
{
  "success": true,
  "status": "PASS",
  "entitlement_id": "uuid",
  "offer_title": "20% Off Coffee",
  "offer_type": "percentage",
  "discount_value": "20%",
  "merchant_name": "Coffee Paradise",
  "student_name": "John Doe"
}
```

**Or using curl**:
```bash
curl -X POST http://localhost:8000/merchant/validate \
  -H "Content-Type: application/json" \
  -d '{"proof_token":"your-token-here"}'
```

---

### Test 2: Confirm Redemption

**Endpoint**: `POST /merchant/confirm`

**In Swagger UI**:
1. Click on `POST /merchant/confirm`
2. Click "Try it out"
3. Request body:
   ```json
   {
     "proof_token": "same-token-from-test-1",
     "merchant_pin": "1234",
     "total_bill_amount": 100.00
   }
   ```
4. Click "Execute"

**Expected Response**:
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
  "redeemed_at": "2026-02-15T13:05:00Z"
}
```

**Or using curl**:
```bash
curl -X POST http://localhost:8000/merchant/confirm \
  -H "Content-Type: application/json" \
  -d '{
    "proof_token":"your-token-here",
    "merchant_pin":"1234",
    "total_bill_amount":100.00
  }'
```

**Copy the `redemption_id` for Test 3!**

---

### Test 3: Void Redemption

**Endpoint**: `POST /merchant/void`

**In Swagger UI**:
1. Click on `POST /merchant/void`
2. Click "Try it out"
3. Request body:
   ```json
   {
     "redemption_id": "paste-redemption-id-from-test-2",
     "merchant_pin": "1234",
     "reason": "Customer returned item"
   }
   ```
4. Click "Execute"

**Expected Response**:
```json
{
  "success": true,
  "message": "Redemption voided successfully",
  "redemption_id": "uuid",
  "voided_at": "2026-02-15T13:10:00Z"
}
```

**Or using curl**:
```bash
curl -X POST http://localhost:8000/merchant/void \
  -H "Content-Type: application/json" \
  -d '{
    "redemption_id":"your-redemption-id",
    "merchant_pin":"1234",
    "reason":"Customer returned item"
  }'
```

---

## Complete Test Flow (Postman/Swagger)

### Flow 1: Successful Redemption

```
1. Student: POST /entitlements/claim
   → Get entitlement_id

2. Student: POST /entitlements/{id}/proof
   → Get proof_token (30s to use!)

3. Merchant: POST /merchant/validate
   → Verify token is valid (PASS)

4. Merchant: POST /merchant/confirm
   → Confirm with PIN and bill amount
   → Get redemption_id

5. Verify in database:
   - Entitlement state = "used"
   - Redemption record created
   - Token deleted from Redis
```

### Flow 2: Void Redemption

```
1-4. Same as Flow 1

5. Merchant: POST /merchant/void
   → Void within 2 hours
   → Provide redemption_id and PIN

6. Verify in database:
   - Redemption is_voided = true
   - Entitlement state = "voided"
```

---

## Error Testing

### Test Invalid Token
```json
{
  "proof_token": "invalid-token-12345"
}
```
**Expected**: `status: "FAIL", reason: "Invalid or expired token"`

### Test Wrong PIN
```json
{
  "proof_token": "valid-token",
  "merchant_pin": "9999",
  "total_bill_amount": 100.00
}
```
**Expected**: `400 Bad Request - "Invalid merchant PIN"`

### Test Expired Void Window
Wait 2+ hours after redemption, then try to void.
**Expected**: `400 Bad Request - "Void window expired"`

---

## Verification Queries

### Check Redemption in Database
```sql
SELECT 
    r.*,
    e.state as entitlement_state,
    o.title as offer_title
FROM redemptions r
JOIN entitlements e ON r.entitlement_id = e.id
JOIN offers o ON r.offer_id = o.id
ORDER BY r.redeemed_at DESC
LIMIT 5;
```

### Check Token in Redis
```bash
# Using redis-cli
redis-cli
> GET sv:app:redeem:token:your-token-here
```

---

## Quick Test Script (Python)

Save as `test_merchant.py`:

```python
import requests
import json

BASE_URL = "http://localhost:8000"

# Replace with your actual token
PROOF_TOKEN = "your-proof-token-here"
MERCHANT_PIN = "1234"

def test_validate():
    print("Testing /merchant/validate...")
    response = requests.post(
        f"{BASE_URL}/merchant/validate",
        json={"proof_token": PROOF_TOKEN}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}\n")
    return response.json()

def test_confirm():
    print("Testing /merchant/confirm...")
    response = requests.post(
        f"{BASE_URL}/merchant/confirm",
        json={
            "proof_token": PROOF_TOKEN,
            "merchant_pin": MERCHANT_PIN,
            "total_bill_amount": 100.00
        }
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}\n")
    return response.json()

def test_void(redemption_id):
    print("Testing /merchant/void...")
    response = requests.post(
        f"{BASE_URL}/merchant/void",
        json={
            "redemption_id": redemption_id,
            "merchant_pin": MERCHANT_PIN,
            "reason": "Test void"
        }
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}\n")

if __name__ == "__main__":
    # Test validate
    validate_result = test_validate()
    
    if validate_result.get("status") == "PASS":
        # Test confirm
        confirm_result = test_confirm()
        
        if confirm_result.get("success"):
            redemption_id = confirm_result["redemption_id"]
            
            # Test void
            test_void(redemption_id)
```

Run: `python test_merchant.py`

---

## Troubleshooting

### "Invalid or expired token"
- Token expired (30s TTL)
- Token already used
- Token not in Redis
→ Generate a new QR token

### "Invalid merchant PIN"
- PIN not set in database
- Wrong PIN provided
→ Check `merchants.pin_hash` column

### "Entitlement is used"
- Token already confirmed
- Cannot reuse tokens
→ Claim a new entitlement

### "Void window expired"
- More than 2 hours since redemption
- Different day than redemption
→ Cannot void old redemptions

---

## Summary

**Easiest way to test**:
1. Start server
2. Open http://localhost:8000/docs
3. Set merchant PIN in database (SQL above)
4. Use student flow to get QR token
5. Test merchant endpoints in Swagger UI

**All endpoints are in the "Merchant Validation" section!**

Good luck! 🚀
