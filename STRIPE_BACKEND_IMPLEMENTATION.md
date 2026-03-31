# Stripe Backend Implementation Guide

This document describes the three backend endpoints the mobile app expects for Stripe ticket payments. The frontend is already wired up — once these endpoints exist, payments will work end-to-end.

---

## Environment Variables

Add these to your backend environment (Railway, `.env`, etc.):

```
STRIPE_SECRET_KEY=sk_test_...           # from Stripe Dashboard > API Keys
STRIPE_WEBHOOK_SECRET=whsec_...         # from Stripe Dashboard > Webhooks (after creating the endpoint)
```

**Never** expose `STRIPE_SECRET_KEY` to the client. The frontend only uses the publishable key.

---

## Install Stripe SDK

```bash
# Python
pip install stripe

# Node.js
npm install stripe
```

---

## Database: Add columns to ticket_records table

Your existing `ticket_records` table (or equivalent) needs these columns if they don't already exist:

| Column | Type | Notes |
|---|---|---|
| `stripe_customer_id` | `VARCHAR` / `TEXT` | Stripe Customer ID (cus_xxx) |
| `stripe_payment_intent_id` | `VARCHAR` / `TEXT` | PaymentIntent ID (pi_xxx) |
| `payment_status` | `VARCHAR` | `"pending"`, `"confirmed"`, `"failed"` |

You may also want to store a `stripe_customer_id` on the **users** table so returning customers reuse the same Stripe Customer object.

---

## Endpoint 1: `POST /payments/tickets/create-payment-intent`

**Auth**: Requires JWT (same as `create-mock-order`)

### Request Body

```json
{
  "ticket_id": "uuid",
  "quantity": 2,
  "visit_date": "2026-04-05",
  "visit_time": null,
  "contact_phone": "+971501234567",
  "contact_email": "user@example.com",
  "special_requests": null
}
```

### What it does (step by step)

1. **Validate** the ticket exists, is active, and the pricing period covers `visit_date`
2. **Calculate total** in the smallest currency unit (fils for AED):
   ```
   amount_in_fils = int(ticket.our_price * quantity * 100)
   # e.g. AED 50.00 × 2 = 10000 fils
   ```
3. **Create or retrieve Stripe Customer** for the authenticated user:
   ```python
   # Python example
   import stripe
   stripe.api_key = STRIPE_SECRET_KEY

   # Check if user already has a stripe_customer_id in your DB
   if user.stripe_customer_id:
       customer = stripe.Customer.retrieve(user.stripe_customer_id)
   else:
       customer = stripe.Customer.create(
           email=contact_email,
           metadata={"user_id": str(user.id)}
       )
       # Save customer.id to user record in your DB
   ```
4. **Create Ephemeral Key** (required by PaymentSheet to let the customer manage saved cards):
   ```python
   ephemeral_key = stripe.EphemeralKey.create(
       customer=customer.id,
       stripe_version="2024-06-20"  # use latest API version
   )
   ```
5. **Create PaymentIntent**:
   ```python
   payment_intent = stripe.PaymentIntent.create(
       amount=amount_in_fils,
       currency="aed",
       customer=customer.id,
       metadata={
           "ticket_id": str(ticket_id),
           "quantity": str(quantity),
           "visit_date": visit_date or "",
           "user_id": str(user.id),
           "record_id": str(record_id),  # set after creating the record below
       }
   )
   ```
6. **Create a pending booking record** in your database:
   ```python
   record = TicketRecord.create(
       user_id=user.id,
       ticket_id=ticket_id,
       quantity=quantity,
       visit_date=visit_date,
       visit_time=visit_time,
       contact_phone=contact_phone,
       contact_email=contact_email,
       special_requests=special_requests,
       total_price=ticket.our_price * quantity,
       stripe_customer_id=customer.id,
       stripe_payment_intent_id=payment_intent.id,
       payment_status="pending"
   )
   ```
7. **Update PaymentIntent metadata** with the record_id:
   ```python
   stripe.PaymentIntent.modify(
       payment_intent.id,
       metadata={**payment_intent.metadata, "record_id": str(record.id)}
   )
   ```

### Response (200 OK)

```json
{
  "payment_intent_client_secret": "pi_3abc...xyz_secret_def...uvw",
  "ephemeral_key_secret": "ek_test_...",
  "customer_id": "cus_abc123",
  "record_id": "uuid-of-booking-record",
  "total_price": 100.00,
  "currency": "aed"
}
```

### Error Responses

| Status | When |
|---|---|
| 400 | Invalid ticket_id, quantity < 1, visit_date outside pricing period |
| 401 | Missing/expired JWT |
| 404 | Ticket not found or inactive |
| 500 | Stripe API error (log it, return generic message) |

---

## Endpoint 2: `POST /payments/tickets/confirm-payment`

**Auth**: Requires JWT

### Request Body

```json
{
  "record_id": "uuid-of-booking-record",
  "payment_intent_id": "pi_3abc...xyz"
}
```

### What it does

1. **Look up the booking record** by `record_id`, verify it belongs to the authenticated user
2. **Retrieve the PaymentIntent** from Stripe and verify its status:
   ```python
   payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)

   if payment_intent.status != "succeeded":
       raise HTTPException(400, "Payment has not succeeded")

   if payment_intent.metadata.get("record_id") != str(record_id):
       raise HTTPException(400, "PaymentIntent does not match this booking")
   ```
3. **Update the booking record** to `"confirmed"`:
   ```python
   record.payment_status = "confirmed"
   record.save()
   ```
4. **Send confirmation email** (same logic as your existing mock order email flow)

### Response (200 OK)

```json
{
  "record_id": "uuid",
  "status": "confirmed",
  "message": "Booking confirmed successfully"
}
```

### Error Responses

| Status | When |
|---|---|
| 400 | PaymentIntent not succeeded, record_id mismatch |
| 401 | Missing/expired JWT |
| 404 | Record not found |

### Important: Idempotency

If the record is **already confirmed**, return 200 with the same response (don't error). The frontend may retry this call if the first attempt appeared to fail due to a network timeout.

---

## Endpoint 3: `POST /stripe/webhook` (Stripe Webhook Handler)

**Auth**: No JWT — authenticated via Stripe signature

This is the **source of truth** for payment status. It handles cases where the frontend confirm call fails (network drop, app crash, etc.).

### Setup

1. Go to [Stripe Dashboard > Webhooks](https://dashboard.stripe.com/webhooks)
2. Add endpoint: `https://svapp-backend-production.up.railway.app/stripe/webhook`
3. Select events: `payment_intent.succeeded`, `payment_intent.payment_failed`
4. Copy the signing secret → set as `STRIPE_WEBHOOK_SECRET` env var

### Implementation

```python
from fastapi import Request, HTTPException
import stripe

@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(400, "Invalid signature")

    if event["type"] == "payment_intent.succeeded":
        payment_intent = event["data"]["object"]
        record_id = payment_intent["metadata"].get("record_id")

        if record_id:
            record = get_record_by_id(record_id)
            if record and record.payment_status != "confirmed":
                record.payment_status = "confirmed"
                record.save()
                send_confirmation_email(record)

    elif event["type"] == "payment_intent.payment_failed":
        payment_intent = event["data"]["object"]
        record_id = payment_intent["metadata"].get("record_id")

        if record_id:
            record = get_record_by_id(record_id)
            if record and record.payment_status == "pending":
                record.payment_status = "failed"
                record.save()

    return {"status": "ok"}
```

### Key Rules

- **Always verify the Stripe signature** — never trust raw POST bodies
- **Must be idempotent** — processing the same event twice should produce the same result (check status before updating)
- **Return 200 quickly** — do heavy work (emails) async/in background if possible; Stripe retries on non-2xx
- **Don't require JWT** — this endpoint is called by Stripe's servers, not by the app

---

## Complete Flow Diagram

```
Mobile App                          Backend                           Stripe
    │                                  │                                │
    ├─ POST /create-payment-intent ──► │                                │
    │                                  ├─ Create Customer ────────────► │
    │                                  ├─ Create EphemeralKey ────────► │
    │                                  ├─ Create PaymentIntent ───────► │
    │                                  ├─ Create pending record         │
    │ ◄── client_secret, keys ────────┤                                │
    │                                  │                                │
    ├─ initPaymentSheet(secrets)       │                                │
    ├─ presentPaymentSheet()           │                                │
    │   (user enters card / Apple Pay) │                                │
    │   ────────────────────────────── card token ──────────────────► │
    │ ◄──────────────────────────────── payment result ◄───────────── │
    │                                  │                                │
    ├─ POST /confirm-payment ────────► │                                │
    │                                  ├─ Retrieve PaymentIntent ─────► │
    │                                  ├─ Verify status == succeeded    │
    │                                  ├─ Update record → confirmed     │
    │                                  ├─ Send confirmation email       │
    │ ◄── { status: "confirmed" } ────┤                                │
    │                                  │                                │
    │                                  │ ◄── webhook: payment_intent   │
    │                                  │     .succeeded (backup)        │
    │                                  ├─ Idempotent confirm            │
```

---

## Testing Checklist

### Test Cards (use with your `pk_test_` / `sk_test_` keys)

| Card Number | Scenario |
|---|---|
| `4242 4242 4242 4242` | Succeeds immediately |
| `4000 0027 6000 3184` | Requires 3D Secure authentication |
| `4000 0000 0000 0002` | Declined |
| `4000 0000 0000 9995` | Insufficient funds |

Use any future expiry date, any 3-digit CVC, any postal code.

### Test Scenarios

- [ ] Happy path: payment succeeds → confirm endpoint → record is "confirmed" → email sent
- [ ] User cancels PaymentSheet → no backend state change, record stays "pending" (clean up stale pending records via a cron job or let them expire)
- [ ] Card declined → PaymentSheet shows error, user can retry or dismiss
- [ ] 3D Secure required → in-app browser opens → returns to PaymentSheet
- [ ] Confirm call fails (simulate by returning 500) → frontend shows soft message → webhook still confirms the record
- [ ] Webhook arrives before confirm call → confirm call sees already-confirmed record → returns 200 (idempotent)
- [ ] Duplicate webhook → no duplicate emails or state changes

### Stripe CLI (local webhook testing)

```bash
# Install: https://stripe.com/docs/stripe-cli
stripe login
stripe listen --forward-to localhost:8000/stripe/webhook
# This prints a whsec_... key — use it as STRIPE_WEBHOOK_SECRET locally
```

---

## Currency Notes

- Currency is **AED** (UAE Dirham)
- Stripe uses **smallest currency unit**: AED 50.00 = `5000` (fils)
- Formula: `amount = int(our_price * quantity * 100)`
- The `currency` field in the response should be `"aed"` (lowercase)

---

## Cleanup: Stale Pending Records

Records in `"pending"` status where the PaymentIntent was never completed should be cleaned up. Options:

1. **Cron job**: Run daily, find records older than 24h with `payment_status = "pending"`, check PaymentIntent status via Stripe API, cancel if not succeeded
2. **Webhook-driven**: Listen for `payment_intent.canceled` events and mark records as `"canceled"`

---

## Production Checklist

- [ ] Swap `sk_test_` for `sk_live_` in backend env vars
- [ ] Frontend: swap `pk_test_` for `pk_live_` in `constants/stripe.ts`
- [ ] Create production webhook endpoint in Stripe Dashboard pointing to your production URL
- [ ] Set production `STRIPE_WEBHOOK_SECRET`
- [ ] Verify webhook signature validation works in production
- [ ] Test with a real card (Stripe test mode → live mode)
