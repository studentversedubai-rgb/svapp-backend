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
