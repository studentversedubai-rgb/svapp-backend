# API Overview

## Base URL
- **Local**: `http://localhost:8000`
- **Production**: `https://api.studentverse.ae`

## Authentication
All protected endpoints require a JWT token in the Authorization header:
```
Authorization: Bearer <jwt_token>
```

---

## Modules

### 1. Authentication (`/auth`)
User authentication and profile management.

**Endpoints:**
- `POST /auth/send-otp` - Send OTP to email
- `POST /auth/verify-otp` - Verify OTP and login
- `POST /auth/register` - Complete user registration
- `GET /auth/me` - Get current user profile
- `PUT /auth/profile` - Update user profile

### 2. Offers (`/offers`)
Browse and search student offers.

**Endpoints:**
- `GET /offers` - List all active offers
- `GET /offers/{id}` - Get offer details
- `GET /offers/featured` - Get featured offers
- `GET /offers/search` - Search offers

### 3. Entitlements (`/entitlements`)
QR-based offer redemption system.

**Endpoints:**
- `POST /entitlements/claim` - Claim an offer
- `POST /entitlements/{id}/proof` - Generate QR code
- `POST /entitlements/validate` - Validate QR code (merchant)
- `POST /entitlements/confirm` - Confirm redemption
- `POST /entitlements/void` - Void a redemption
- `GET /entitlements/my` - Get user's entitlements
- `GET /entitlements/savings` - Get savings summary

### 4. Orbit AI (`/orbit`)
AI-powered recommendations and planning.

**Endpoints:**
- `POST /orbit/chat` - Chat with AI assistant
- `GET /orbit/recommendations` - Get personalized recommendations
- `GET /orbit/nearby` - Get nearby offers

### 5. Merchant Validation (`/merchant`)
Public endpoints for merchant-side QR validation and redemption.

**Endpoints:**
- `POST /merchant/validate` - Validate student's QR proof token
- `POST /merchant/confirm` - Confirm redemption with PIN and bill amount
- `POST /merchant/void` - Void a redemption within void window
- `GET /merchant/health` - Health check for merchant endpoints

**Notes:**
- All endpoints are **public** (no JWT authentication required)
- `/confirm` and `/void` require merchant PIN for authorization
- QR tokens have 30-second TTL
- Void window is 2 hours from redemption time

### 6. Tickets (`/tickets`)
Browse available tickets and manage booking records.

**Endpoints:**
- `GET /tickets` — List all active tickets within current pricing period. Optional `?merchant_name=` filter (case-insensitive). **Public.**
- `GET /tickets/{ticket_id}` — Get a single active ticket by ID. Returns 404 if not found or inactive. **Public.**
- `GET /tickets/records/me` — Get all ticket booking records for the authenticated user (ordered by created_at DESC). **Requires JWT.**
- `PATCH /tickets/records/{record_id}/status` — Update status, e_ticket_url, internal_notes, fulfilled_at on a record. Auto-sets fulfilled_at when status=`fulfilled`. **Admin only.**

**Notes:**
- Public ticket endpoints filter by `is_active=true` AND today's date within `pricing_period_start`…`pricing_period_end`
- Admin check uses the `role` field in `public.users` (value: `"admin"`)

### 7. Payments (`/payments`)
Stripe payment processing and CSV export for ticket bookings.

**Endpoints:**
- `POST /payments/tickets/create-intent` — Create a Stripe PaymentIntent for a ticket. Creates a pending `ticket_records` row. Returns `client_secret`, `record_id`, `total_price`. **Requires JWT.**
- `POST /payments/webhook/stripe` — Stripe webhook receiver. Verifies `Stripe-Signature` header, processes `payment_intent.succeeded`, sends confirmation emails via Postmark. Always returns 200. **Public.**
- `GET /payments/tickets/records/export` — Download all ticket_records as CSV. Optional `?from_date=` and `?to_date=` filters (YYYY-MM-DD). **Admin only.**

**Environment Variables (set in Railway):**
- `STRIPE_SECRET_KEY` — Stripe secret key
- `STRIPE_WEBHOOK_SECRET` — Stripe webhook endpoint secret
- `STRIPE_CURRENCY` — Defaults to `aed`
- `INTERNAL_BOOKINGS_EMAIL` — Recipient for internal booking notifications

---

## Response Format

### Success Response
```json
{
  "success": true,
  "data": { ... },
  "message": "Operation successful"
}
```

### Error Response
```json
{
  "detail": "Error message"
}
```

---

## Rate Limiting
- **Default**: 60 requests per minute per IP
- **Orbit Chat**: 150 messages per day per user

---

## Interactive Documentation
- **Swagger UI**: `/docs`
- **ReDoc**: `/redoc`
