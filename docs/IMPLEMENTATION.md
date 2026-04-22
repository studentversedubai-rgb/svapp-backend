# StudentVerse Backend API - Implementation Guide

**Base URL (Production):** `https://svapp-backend-production.up.railway.app`  
**Base URL (Local):** `http://localhost:8000`

**Interactive Documentation:**
- Swagger UI: `{BASE_URL}/docs`
- ReDoc: `{BASE_URL}/redoc`

---

## Table of Contents

1. [Authentication Flow](#1-authentication-flow)
2. [Offers Module](#2-offers-module)
3. [Entitlements & Redemption](#3-entitlements--redemption)
4. [Merchant Validation](#4-merchant-validation)
5. [Orbit AI](#5-orbit-ai)
6. [Error Handling](#6-error-handling)
7. [Security & Best Practices](#7-security--best-practices)

---

## 1. Authentication Flow

### Overview
StudentVerse uses OTP-based authentication with JWT tokens. No passwords are stored.

### 1.1 Send OTP

**Endpoint:** `POST /auth/send-otp`  
**Authentication:** None  
**Rate Limit:** 60 requests/minute

**Request:**
```json
{
  "email": "student@university.edu"
}
```

**Response:**
```json
{
  "ok": true,
  "data": {
    "message": "OTP sent successfully",
    "email": "student@university.edu"
  }
}
```

**Implementation Notes:**
- Email must be a valid university email
- OTP is sent via Resend email service
- OTP expires in 5 minutes
- Store email in state for next step

---

### 1.2 Verify OTP & Get Token

**Endpoint:** `POST /auth/verify-otp`  
**Authentication:** None  
**Rate Limit:** 60 requests/minute

**Request:**
```json
{
  "email": "student@university.edu",
  "code": "123456"
}
```

**Response:**
```json
{
  "ok": true,
  "data": {
    "tokens": {
      "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "expires_in": 3600
    },
    "user": {
      "id": "uuid",
      "email": "student@university.edu",
      "first_name": null,
      "last_name": null
    },
    "is_new_user": true
  }
}
```


**Implementation Notes:**
- Store `access_token` securely (AsyncStorage, SecureStore)
- Use `access_token` in Authorization header for all protected endpoints
- If `is_new_user: true`, redirect to registration/profile completion
- Token format: `Bearer {access_token}`

---

### 1.3 Complete Registration

**Endpoint:** `POST /auth/register`  
**Authentication:** Required (JWT from verify-otp)  
**Rate Limit:** 60 requests/minute

**Headers:**
```
Authorization: Bearer {access_token}
X-Device-ID: {unique_device_identifier} (optional)
```

**Request:**
```json
{
  "email": "student@university.edu",
  "first_name": "John",
  "last_name": "Doe",
  "nationality": "UAE",
  "university": "University of Dubai",
  "phone_number": "+971501234567",
  "age": 22,
  "avatar_url": "https://example.com/avatar.jpg",
  "device_id": "device-uuid-123"
}
```

**Response:**
```json
{
  "ok": true,
  "data": {
    "id": "uuid",
    "email": "student@university.edu",
    "first_name": "John",
    "last_name": "Doe",
    "full_name": "John Doe",
    "nationality": "UAE",
    "university": "University of Dubai",
    "phone_number": "+971501234567",
    "age": 22,
    "avatar_url": "https://example.com/avatar.jpg",
    "account_type": "free"
  }
}
```

**Implementation Notes:**
- All fields except `email`, `first_name`, `last_name` are optional
- `device_id` enables single-device login security
- Email is immutable after registration

---

### 1.4 Get Current User Profile

**Endpoint:** `GET /auth/me`  
**Authentication:** Required  
**Rate Limit:** 100 requests/minute

**Headers:**
```
Authorization: Bearer {access_token}
X-Device-ID: {device_id} (optional but recommended)
```

**Response:**
```json
{
  "ok": true,
  "data": {
    "id": "uuid",
    "email": "student@university.edu",
    "first_name": "John",
    "last_name": "Doe",
    "full_name": "John Doe",
    "nationality": "UAE",
    "university": "University of Dubai",
    "phone_number": "+971501234567",
    "age": 22,
    "avatar_url": "https://example.com/avatar.jpg",
    "account_type": "free"
  }
}
```

**Implementation Notes:**
- Use this to check authentication status
- Call on app launch to restore user session
- If 401 response, redirect to login

---

### 1.5 Update Profile

**Endpoint:** `PUT /auth/profile`  
**Authentication:** Required  
**Rate Limit:** 60 requests/minute

**Headers:**
```
Authorization: Bearer {access_token}
```

**Request:**
```json
{
  "university": "American University of Dubai",
  "nationality": "UAE",
  "phone_number": "+971501234567",
  "avatar_url": "https://example.com/new-avatar.jpg"
}
```

**Response:**
```json
{
  "ok": true,
  "data": {
    "id": "uuid",
    "email": "student@university.edu",
    "first_name": "John",
    "last_name": "Doe",
    "full_name": "John Doe",
    "nationality": "UAE",
    "university": "American University of Dubai",
    "phone_number": "+971501234567",
    "avatar_url": "https://example.com/new-avatar.jpg",
    "account_type": "free"
  }
}
```

**Implementation Notes:**
- Cannot update: `email`, `first_name`, `last_name`, `device_id`
- All fields are optional
- Only send fields that changed

---

### 1.6 Get User Analytics

**Endpoint:** `GET /auth/profile/analytics`  
**Authentication:** Required  
**Rate Limit:** 100 requests/minute

**Headers:**
```
Authorization: Bearer {access_token}
```

**Response:**
```json
{
  "ok": true,
  "data": {
    "total_saved": 450.00,
    "total_spent": 1200.00,
    "total_redemptions": 15,
    "subscription_status": "free"
  }
}
```

**Implementation Notes:**
- Use for profile/dashboard screens
- Shows lifetime savings and redemptions

---

### 1.7 Logout

**Endpoint:** `POST /auth/logout`  
**Authentication:** Required  
**Rate Limit:** 60 requests/minute

**Headers:**
```
Authorization: Bearer {access_token}
```

**Response:**
```json
{
  "message": "Logged out successfully"
}
```

**Implementation Notes:**
- Backend is stateless, so just clear local token
- Remove token from AsyncStorage/SecureStore
- Clear any cached user data

---

## 2. Offers Module

### Overview
Browse, search, and discover student offers with location-based filtering.

### 2.1 Get Home Feed

**Endpoint:** `GET /offers/home`  
**Authentication:** Required  
**Rate Limit:** 100 requests/minute

**Headers:**
```
Authorization: Bearer {access_token}
```

**Query Parameters:**
- `latitude` (optional): User latitude (-90 to 90)
- `longitude` (optional): User longitude (-180 to 180)
- `page` (optional): Page number (default: 1, min: 1)
- `page_size` (optional): Items per page (default: 20, min: 1, max: 100)

**Example Request:**
```
GET /offers/home?latitude=25.2048&longitude=55.2708&page=1&page_size=20
```

**Response:**
```json
{
  "items": [
    {
      "id": "offer-uuid",
      "title": "20% Off All Items",
      "description": "Get 20% discount on your entire purchase",
      "merchant": {
        "id": "merchant-uuid",
        "name": "Coffee Shop",
        "logo_url": "https://example.com/logo.jpg",
        "latitude": 25.2048,
        "longitude": 55.2708
      },
      "category": {
        "id": "category-uuid",
        "name": "Food & Beverage",
        "slug": "food-beverage",
        "icon_url": "https://example.com/icon.png",
        "sort_order": 1
      },
      "offer_type": "percentage",
      "discount_value": "20%",
      "original_price": null,
      "discounted_price": null,
      "image_url": "https://example.com/offer.jpg",
      "valid_from": "2026-02-01T00:00:00Z",
      "valid_until": "2026-02-28T23:59:59Z",
      "distance_km": 2.5,
      "is_featured": true,
      "created_at": "2026-01-15T10:00:00Z"
    }
  ],
  "total": 45,
  "page": 1,
  "page_size": 20,
  "total_pages": 3
}
```


**Implementation Notes:**
- If location provided, results sorted by distance (nearest first)
- If no location, sorted by `created_at` (newest first)
- Both `latitude` and `longitude` must be provided together
- Only returns active, eligible offers (date/time/day validation applied)
- `distance_km` is `null` if merchant has no location or user didn't provide location
- Use for main home screen

**Eligibility Filters Applied:**
- Offer is active (`is_active: true`)
- Merchant is active
- Current date within `valid_from` and `valid_until`
- Current time within `time_valid_from` and `time_valid_until` (if set)
- Current day in `valid_days_of_week` (if set)

---

### 2.2 Search Offers

**Endpoint:** `GET /offers/search`  
**Authentication:** Required  
**Rate Limit:** 60 requests/minute

**Headers:**
```
Authorization: Bearer {access_token}
```

**Query Parameters:**
- `query` (optional): Search keyword (min: 2 chars, max: 200 chars)
- `category_id` (optional): Filter by category UUID
- `latitude` (optional): User latitude (-90 to 90)
- `longitude` (optional): User longitude (-180 to 180)
- `radius_km` (optional): Search radius in km (min: 0, max: 50)
- `page` (optional): Page number (default: 1)
- `page_size` (optional): Items per page (default: 20, max: 100)

**Example Request:**
```
GET /offers/search?query=coffee&category_id=cat-uuid&latitude=25.2048&longitude=55.2708&radius_km=10&page=1&page_size=20
```

**Response:**
```json
{
  "items": [
    {
      "id": "offer-uuid",
      "title": "Free Coffee with Any Meal",
      "description": "Get a free coffee when you order any meal",
      "merchant": {
        "id": "merchant-uuid",
        "name": "Cafe Dubai",
        "logo_url": "https://example.com/logo.jpg",
        "latitude": 25.2048,
        "longitude": 55.2708
      },
      "category": {
        "id": "category-uuid",
        "name": "Food & Beverage",
        "slug": "food-beverage",
        "icon_url": "https://example.com/icon.png",
        "sort_order": 1
      },
      "offer_type": "bogo",
      "discount_value": null,
      "original_price": 15.00,
      "discounted_price": null,
      "image_url": "https://example.com/offer.jpg",
      "valid_from": "2026-02-01T00:00:00Z",
      "valid_until": "2026-02-28T23:59:59Z",
      "distance_km": 3.2,
      "is_featured": false,
      "created_at": "2026-01-20T14:30:00Z"
    }
  ],
  "total": 12,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

**Implementation Notes:**
- `query` searches in offer title and description
- `radius_km` requires both `latitude` and `longitude`
- Both `latitude` and `longitude` must be provided together
- Query is sanitized to prevent SQL injection
- Max radius enforced at 50km
- Use for search screen with filters

**Validation Rules:**
- Query must be at least 2 characters
- Dangerous SQL characters are rejected
- Radius cannot exceed 50km

---

### 2.3 Get Nearby Offers

**Endpoint:** `GET /offers/nearby`  
**Authentication:** Required  
**Rate Limit:** 100 requests/minute

**Headers:**
```
Authorization: Bearer {access_token}
```

**Query Parameters:**
- `latitude` (required): User latitude (-90 to 90)
- `longitude` (required): User longitude (-180 to 180)
- `radius_km` (optional): Search radius in km (default: 5, min: 0.1, max: 50)
- `category_id` (optional): Filter by category UUID
- `page` (optional): Page number (default: 1)
- `page_size` (optional): Items per page (default: 20, max: 100)

**Example Request:**
```
GET /offers/nearby?latitude=25.2048&longitude=55.2708&radius_km=5&page=1&page_size=20
```

**Response:**
```json
{
  "items": [
    {
      "id": "offer-uuid",
      "title": "Student Discount - 15% Off",
      "description": "Show your student ID for 15% off",
      "merchant": {
        "id": "merchant-uuid",
        "name": "Bookstore",
        "logo_url": "https://example.com/logo.jpg",
        "latitude": 25.2050,
        "longitude": 55.2710
      },
      "category": {
        "id": "category-uuid",
        "name": "Shopping",
        "slug": "shopping",
        "icon_url": "https://example.com/icon.png",
        "sort_order": 3
      },
      "offer_type": "percentage",
      "discount_value": "15%",
      "original_price": null,
      "discounted_price": null,
      "image_url": "https://example.com/offer.jpg",
      "valid_from": "2026-02-01T00:00:00Z",
      "valid_until": "2026-03-31T23:59:59Z",
      "distance_km": 0.8,
      "is_featured": false,
      "created_at": "2026-01-18T09:15:00Z"
    }
  ],
  "total": 8,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

**Implementation Notes:**
- Results always sorted by distance (nearest first)
- Both `latitude` and `longitude` are required
- Default radius is 5km
- Use for "Near Me" or map view screens
- Only returns offers within specified radius

---

### 2.4 Get Offer Details

**Endpoint:** `GET /offers/{offer_id}`  
**Authentication:** Required  
**Rate Limit:** 100 requests/minute

**Headers:**
```
Authorization: Bearer {access_token}
```

**Query Parameters:**
- `latitude` (optional): User latitude for distance calculation
- `longitude` (optional): User longitude for distance calculation

**Example Request:**
```
GET /offers/770e8400-e29b-41d4-a716-446655440000?latitude=25.2048&longitude=55.2708
```

**Response:**
```json
{
  "id": "offer-uuid",
  "title": "Buy One Get One Free",
  "description": "Purchase any item and get another one free",
  "terms_conditions": "Valid on items of equal or lesser value. Cannot be combined with other offers.",
  "merchant": {
    "id": "merchant-uuid",
    "name": "Pizza Place",
    "logo_url": "https://example.com/logo.jpg",
    "description": "Best pizza in Dubai",
    "address": "123 Main Street, Dubai Marina",
    "latitude": 25.0800,
    "longitude": 55.1400
  },
  "category": {
    "id": "category-uuid",
    "name": "Food & Beverage",
    "slug": "food-beverage",
    "description": "Restaurants, cafes, and food delivery",
    "icon_url": "https://example.com/icon.png",
    "sort_order": 1
  },
  "offer_type": "bogo",
  "discount_value": null,
  "original_price": 45.00,
  "discounted_price": null,
  "image_url": "https://example.com/offer-main.jpg",
  "images": [
    "https://example.com/offer-1.jpg",
    "https://example.com/offer-2.jpg",
    "https://example.com/offer-3.jpg"
  ],
  "valid_from": "2026-02-01T00:00:00Z",
  "valid_until": "2026-02-28T23:59:59Z",
  "time_valid_from": "17:00:00",
  "time_valid_until": "22:00:00",
  "valid_days_of_week": [1, 2, 3, 4, 5],
  "max_claims_per_user": 1,
  "total_claims": 234,
  "max_total_claims": 1000,
  "is_featured": true,
  "distance_km": 5.2,
  "created_at": "2026-01-10T08:00:00Z",
  "updated_at": "2026-01-25T12:30:00Z"
}
```


**Implementation Notes:**
- Returns 404 if offer not found or not eligible
- `distance_km` is `null` if location not provided or merchant has no location
- `time_valid_from` and `time_valid_until` are in HH:MM:SS format (24-hour)
- `valid_days_of_week` uses ISO format: 1=Monday, 7=Sunday
- Use for offer detail screen before claiming
- Show terms & conditions prominently

**Offer Types:**
- `percentage`: Discount as percentage (e.g., "20%")
- `bogo`: Buy One Get One (original_price is the free item value)
- `bundle`: Bundle deal (original_price vs discounted_price)
- `fixed`: Fixed amount off

---

### 2.5 Get Categories

**Endpoint:** `GET /offers/categories/list`  
**Authentication:** Required  
**Rate Limit:** 100 requests/minute

**Headers:**
```
Authorization: Bearer {access_token}
```

**Response:**
```json
{
  "categories": [
    {
      "id": "category-uuid-1",
      "name": "Food & Beverage",
      "slug": "food-beverage",
      "description": "Restaurants, cafes, and food delivery",
      "icon_url": "https://example.com/icons/food.png",
      "sort_order": 1
    },
    {
      "id": "category-uuid-2",
      "name": "Entertainment",
      "slug": "entertainment",
      "description": "Movies, concerts, and events",
      "icon_url": "https://example.com/icons/entertainment.png",
      "sort_order": 2
    },
    {
      "id": "category-uuid-3",
      "name": "Shopping",
      "slug": "shopping",
      "description": "Retail stores and online shopping",
      "icon_url": "https://example.com/icons/shopping.png",
      "sort_order": 3
    }
  ]
}
```

**Implementation Notes:**
- Returns all active categories
- Sorted by `sort_order` (ascending)
- Use for category filters and navigation
- Cache this response (updates infrequently)

---

## 3. Entitlements & Redemption

### Overview
QR-based redemption system with state machine lifecycle.

**Entitlement States:**
- `ACTIVE`: Claimed and ready to redeem
- `PENDING_CONFIRMATION`: QR validated, awaiting merchant confirmation
- `USED`: Successfully redeemed
- `VOIDED`: Reversed within 2-hour window (terminal)
- `EXPIRED`: Time-based expiry (terminal)

### 3.1 Claim Entitlement

**Endpoint:** `POST /entitlements/claim`  
**Authentication:** Required  
**Rate Limit:** 60 requests/minute

**Headers:**
```
Authorization: Bearer {access_token}
X-Device-ID: {device_id} (optional but recommended)
```

**Request:**
```json
{
  "offer_id": "offer-uuid",
  "device_id": "device-uuid-123"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Entitlement claimed successfully",
  "entitlement_id": "entitlement-uuid",
  "offer_id": "offer-uuid",
  "expires_at": "2026-02-01T23:59:59Z"
}
```

**Error Response (Daily Limit):**
```json
{
  "detail": "Daily claim limit reached for this offer"
}
```

**Implementation Notes:**
- One entitlement per user per offer per day
- Offer must be active and valid
- Entitlement expires at end of day (23:59:59)
- `device_id` enables fraud prevention
- Store `entitlement_id` for next steps

**Business Rules:**
- Daily limit: 1 claim per user per offer
- Voided entitlements don't count toward limit
- Expired entitlements are automatically cleaned up

---

### 3.2 Generate QR Proof Token

**Endpoint:** `POST /entitlements/{entitlement_id}/proof`  
**Authentication:** Required  
**Rate Limit:** 100 requests/minute

**Headers:**
```
Authorization: Bearer {access_token}
```

**Example Request:**
```
POST /entitlements/ent-uuid-123/proof
```

**Response:**
```json
{
  "success": true,
  "proof_token": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
  "expires_at": "2026-02-01T15:45:30Z",
  "ttl_seconds": 30
}
```

**Implementation Notes:**
- Token expires in 30 seconds
- Single-use token (deleted after validation)
- Generate QR code from `proof_token` on frontend
- Show countdown timer (30 seconds)
- Allow regeneration if expired
- Token stored in Redis with key: `sv:app:redeem:token:{token}`

**QR Code Generation:**
```javascript
// Example using react-native-qrcode-svg
import QRCode from 'react-native-qrcode-svg';

<QRCode
  value={proof_token}
  size={250}
  backgroundColor="white"
  color="black"
/>
```

---

### 3.3 Get My Entitlements

**Endpoint:** `GET /entitlements/my`  
**Authentication:** Required  
**Rate Limit:** 100 requests/minute

**Headers:**
```
Authorization: Bearer {access_token}
```

**Query Parameters:**
- `state` (optional): Filter by state (`active`, `used`, `voided`, `expired`)

**Example Request:**
```
GET /entitlements/my?state=active
```

**Response:**
```json
[
  {
    "id": "entitlement-uuid",
    "offer_title": "20% Off All Items",
    "merchant_name": "Coffee Shop",
    "state": "active",
    "claimed_at": "2026-02-01T10:00:00Z",
    "expires_at": "2026-02-01T23:59:59Z"
  },
  {
    "id": "entitlement-uuid-2",
    "offer_title": "Buy One Get One Free",
    "merchant_name": "Pizza Place",
    "state": "used",
    "claimed_at": "2026-01-31T14:30:00Z",
    "expires_at": "2026-01-31T23:59:59Z"
  }
]
```

**Implementation Notes:**
- Returns user's entitlements
- Filter by state for different tabs (Active, Used, History)
- Use for "My Offers" or "Wallet" screen
- Show countdown for active entitlements

---

### 3.4 Get User Savings Summary

**Endpoint:** `GET /entitlements/savings`  
**Authentication:** Required  
**Rate Limit:** 100 requests/minute

**Headers:**
```
Authorization: Bearer {access_token}
```

**Response:**
```json
{
  "total_redemptions": 15,
  "total_savings": 450.00,
  "total_spent": 1200.00
}
```

**Implementation Notes:**
- Shows lifetime savings
- Use for profile/dashboard screens
- Display as badges or stats cards

---

## 4. Merchant Validation

### Overview
Public endpoints for merchant-side QR validation and redemption. These endpoints do NOT require student JWT authentication but use merchant PIN for authorization.

### 4.1 Validate QR Token

**Endpoint:** `POST /merchant/validate`  
**Authentication:** None (Public)  
**Rate Limit:** 100 requests/minute per IP

**Request:**
```json
{
  "proof_token": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
}
```

**Response (Success - PASS):**
```json
{
  "success": true,
  "status": "PASS",
  "reason": null,
  "entitlement_id": "entitlement-uuid",
  "offer_title": "20% Off All Items",
  "offer_type": "percentage",
  "discount_value": "20%",
  "merchant_name": "Coffee Shop",
  "student_name": "John Doe",
  "original_price": null,
  "discounted_price": null
}
```

**Response (Failure - FAIL):**
```json
{
  "success": false,
  "status": "FAIL",
  "reason": "Invalid or expired token"
}
```


**Implementation Notes:**
- Merchant scans student's QR code
- Token must be valid and not expired (30s TTL)
- Entitlement must be in ACTIVE state
- On PASS, entitlement moves to PENDING_CONFIRMATION
- Show offer details to merchant for verification
- Merchant proceeds to confirmation with bill amount

**Validation Checks:**
- Token exists in Redis
- Token not expired (30s)
- Entitlement is ACTIVE
- Entitlement not expired
- Device binding (if applicable)

---

### 4.2 Confirm Redemption

**Endpoint:** `POST /merchant/confirm`  
**Authentication:** None (Public, requires merchant PIN)  
**Rate Limit:** 60 requests/minute per IP

**Request:**
```json
{
  "proof_token": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
  "merchant_pin": "1234",
  "total_bill_amount": 100.00
}
```

**Response:**
```json
{
  "success": true,
  "message": "Redemption confirmed successfully",
  "redemption_id": "redemption-uuid",
  "entitlement_id": "entitlement-uuid",
  "total_bill": 100.00,
  "discount_amount": 20.00,
  "final_amount": 80.00,
  "savings": 20.00,
  "redeemed_at": "2026-02-01T15:46:00Z"
}
```

**Error Response (Invalid PIN):**
```json
{
  "detail": "Invalid merchant PIN"
}
```

**Implementation Notes:**
- Merchant enters bill amount and PIN
- Discount calculated server-side based on offer type
- Creates redemption record
- Marks entitlement as USED
- Deletes Redis token (single-use)
- Student receives notification (future feature)

**Discount Calculation by Offer Type:**
- **Percentage**: `discount = total_bill * (percentage / 100)`
- **BOGO**: `discount = original_price` (from offer)
- **Bundle**: `discount = original_price - discounted_price`
- **Fixed**: `discount = fixed_amount`

---

### 4.3 Void Redemption

**Endpoint:** `POST /merchant/void`  
**Authentication:** None (Public, requires merchant PIN)  
**Rate Limit:** 60 requests/minute per IP

**Request:**
```json
{
  "redemption_id": "redemption-uuid",
  "merchant_pin": "1234",
  "reason": "Customer returned item"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Redemption voided successfully",
  "redemption_id": "redemption-uuid",
  "voided_at": "2026-02-01T16:00:00Z"
}
```

**Error Response (Outside Void Window):**
```json
{
  "detail": "Void window expired (2 hours)"
}
```

**Implementation Notes:**
- Only USED redemptions can be voided
- Must be within 2 hours of redemption
- Must be same day as redemption
- Requires merchant PIN
- Marks redemption as voided
- Marks entitlement as VOIDED (terminal state)
- Reason required for audit log

**Business Rules:**
- Void window: 2 hours from redemption time
- Same day only (no next-day voids)
- Reason must be 3-500 characters

---

### 4.4 Merchant Health Check

**Endpoint:** `GET /merchant/health`  
**Authentication:** None (Public)  
**Rate Limit:** None

**Response:**
```json
{
  "status": "ok",
  "service": "merchant-validation"
}
```

**Implementation Notes:**
- Use for connectivity checks
- Verify merchant endpoints are reachable

---

## 5. Orbit AI

### Overview
AI-powered activity planner using RAG (Retrieval-Augmented Generation). Orbit retrieves real offers from the database and uses LLM for natural presentation.

**Important Constraints:**
- Retrieval-only (no hallucinated data)
- Only suggests partner offers from database
- Uses scoring + orchestration + LLM presentation

### 5.1 Chat with Orbit

**Endpoint:** `POST /orbit/chat`  
**Authentication:** Required  
**Rate Limit:** 
- Velocity: 10 requests per minute
- Daily: 150 requests per 24 hours

**Headers:**
```
Authorization: Bearer {access_token}
```

**Request:**
```json
{
  "message": "I want to plan a date night in Dubai Marina",
  "session_id": "session-uuid-123",
  "latitude": 25.0800,
  "longitude": 55.1400,
  "mode": "plan"
}
```

**Response:**
```json
{
  "content": "Perfect! I found some amazing spots for your date night in Dubai Marina! 🌟",
  "plans": [
    {
      "id": "offer-uuid-1",
      "title": "Romantic Dinner - 25% Off",
      "description": "Enjoy a romantic dinner with stunning marina views",
      "merchant_name": "Seaside Restaurant",
      "address": "Dubai Marina Walk, Dubai",
      "latitude": 25.0800,
      "longitude": 55.1400,
      "distance_km": 0.5,
      "tags": {
        "category": "Food & Beverage",
        "cuisine": "Italian",
        "price_range": "$$"
      },
      "highlights": [
        "Marina view",
        "Romantic ambiance",
        "Live music"
      ]
    },
    {
      "id": "offer-uuid-2",
      "title": "Movie Tickets - Buy 1 Get 1 Free",
      "description": "Watch the latest blockbuster together",
      "merchant_name": "Cinema Dubai",
      "address": "Dubai Marina Mall, Dubai",
      "latitude": 25.0820,
      "longitude": 55.1420,
      "distance_km": 0.8,
      "tags": {
        "category": "Entertainment",
        "type": "Cinema"
      },
      "highlights": [
        "Latest releases",
        "Premium seating",
        "Dolby Atmos"
      ]
    },
    {
      "id": "offer-uuid-3",
      "title": "Dessert - 20% Off",
      "description": "End your night with delicious desserts",
      "merchant_name": "Sweet Treats Cafe",
      "address": "JBR Walk, Dubai",
      "latitude": 25.0750,
      "longitude": 55.1350,
      "distance_km": 1.2,
      "tags": {
        "category": "Food & Beverage",
        "type": "Cafe"
      },
      "highlights": [
        "Artisan desserts",
        "Cozy atmosphere",
        "Late night hours"
      ]
    }
  ],
  "session_id": "session-uuid-123",
  "metadata": {
    "total_offers_retrieved": 15,
    "offers_shown": 3,
    "retrieval_time_ms": 120,
    "llm_time_ms": 850
  }
}
```

**Rate Limit Error (429):**
```json
{
  "detail": "Whoa there! 🐢 You're typing too fast! Slow down and try again in a moment."
}
```

**Daily Limit Error (429):**
```json
{
  "detail": "You've reached your daily AI chat limit (150 messages). 😴 Come back tomorrow for more amazing recommendations!"
}
```

**Implementation Notes:**
- `session_id` is optional for first message, returned in response
- Use same `session_id` for conversation continuity
- `latitude` and `longitude` optional but recommended for distance calculation
- `mode` determines AI behavior:
  - `chat`: Casual conversation, witty persona
  - `find`: Focused discovery, specific recommendations
  - `plan`: Structured itinerary creation
- Rate limits checked BEFORE processing (saves API costs)
- Show countdown or disable button when rate limited

**Orbit Modes:**
- **CHAT**: Casual, witty, conversational (default)
- **FIND**: Focused, specific, discovery-oriented
- **PLAN**: Structured, itinerary-based, organized

**Example Use Cases:**
- "Find me coffee shops near campus" (FIND mode)
- "Plan a study break with friends" (PLAN mode)
- "What's good for dinner tonight?" (CHAT mode)

---

## 6. Error Handling

### Standard Error Response Format

All errors follow this structure:

```json
{
  "detail": "Error message"
}
```

### HTTP Status Codes

| Code | Meaning | Common Causes |
|------|---------|---------------|
| 400 | Bad Request | Invalid input, validation failed |
| 401 | Unauthorized | Missing or invalid JWT token |
| 403 | Forbidden | Device mismatch, insufficient permissions |
| 404 | Not Found | Resource doesn't exist or not eligible |
| 422 | Unprocessable Entity | Pydantic validation failed |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server-side error |
| 503 | Service Unavailable | Feature disabled or service down |


### Common Error Scenarios

#### 401 Unauthorized
```json
{
  "detail": "Invalid or expired token"
}
```
**Action:** Redirect to login, clear stored token

#### 403 Forbidden (Device Mismatch)
```json
{
  "detail": "Device mismatch. Single device login enforced."
}
```
**Action:** Show "Login from another device detected" message, force re-login

#### 404 Not Found
```json
{
  "detail": "Offer not found or not eligible"
}
```
**Action:** Show "Offer unavailable" message, refresh list

#### 422 Validation Error
```json
{
  "detail": "[{'loc': ['body', 'email'], 'msg': 'value is not a valid email address', 'type': 'value_error.email'}]"
}
```
**Action:** Parse and show field-specific errors

#### 429 Rate Limit
```json
{
  "detail": "Whoa there! 🐢 You're typing too fast! Slow down and try again in a moment."
}
```
**Action:** Show rate limit message, disable button temporarily

---

## 7. Security & Best Practices

### 7.1 Authentication

**Token Storage:**
```javascript
// React Native example
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';

// Store token securely
await SecureStore.setItemAsync('access_token', token);

// Retrieve token
const token = await SecureStore.getItemAsync('access_token');

// Clear token on logout
await SecureStore.deleteItemAsync('access_token');
```

**Authorization Header:**
```javascript
// Axios example
import axios from 'axios';

const api = axios.create({
  baseURL: 'https://svapp-backend-production.up.railway.app',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add token to all requests
api.interceptors.request.use((config) => {
  const token = await SecureStore.getItemAsync('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 responses
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      // Clear token and redirect to login
      await SecureStore.deleteItemAsync('access_token');
      // Navigate to login screen
    }
    return Promise.reject(error);
  }
);
```

---

### 7.2 Device Binding

**Generate Device ID:**
```javascript
// React Native example
import * as Device from 'expo-device';
import * as Application from 'expo-application';

const getDeviceId = async () => {
  // Use a combination of device identifiers
  const deviceId = `${Device.osName}-${Device.modelName}-${Application.androidId || Application.getIosIdForVendorAsync()}`;
  return deviceId;
};

// Store device ID
const deviceId = await getDeviceId();
await AsyncStorage.setItem('device_id', deviceId);
```

**Include in Requests:**
```javascript
// Add X-Device-ID header
api.interceptors.request.use(async (config) => {
  const deviceId = await AsyncStorage.getItem('device_id');
  if (deviceId) {
    config.headers['X-Device-ID'] = deviceId;
  }
  return config;
});
```

---

### 7.3 Location Services

**Request Location Permission:**
```javascript
// React Native example
import * as Location from 'expo-location';

const getLocation = async () => {
  // Request permission
  const { status } = await Location.requestForegroundPermissionsAsync();
  
  if (status !== 'granted') {
    console.log('Location permission denied');
    return null;
  }
  
  // Get current location
  const location = await Location.getCurrentPositionAsync({
    accuracy: Location.Accuracy.Balanced,
  });
  
  return {
    latitude: location.coords.latitude,
    longitude: location.coords.longitude,
  };
};
```

**Use in API Calls:**
```javascript
// Home feed with location
const location = await getLocation();
const response = await api.get('/offers/home', {
  params: {
    latitude: location?.latitude,
    longitude: location?.longitude,
    page: 1,
    page_size: 20,
  },
});
```

---

### 7.4 QR Code Generation

**Generate QR Code:**
```javascript
// React Native example
import QRCode from 'react-native-qrcode-svg';
import { useState, useEffect } from 'react';

const QRCodeScreen = ({ entitlementId }) => {
  const [proofToken, setProofToken] = useState(null);
  const [expiresAt, setExpiresAt] = useState(null);
  const [timeLeft, setTimeLeft] = useState(30);
  
  useEffect(() => {
    generateQRCode();
  }, []);
  
  useEffect(() => {
    if (!expiresAt) return;
    
    const interval = setInterval(() => {
      const now = new Date();
      const expiry = new Date(expiresAt);
      const secondsLeft = Math.max(0, Math.floor((expiry - now) / 1000));
      
      setTimeLeft(secondsLeft);
      
      if (secondsLeft === 0) {
        clearInterval(interval);
        // Auto-regenerate or show expired message
      }
    }, 1000);
    
    return () => clearInterval(interval);
  }, [expiresAt]);
  
  const generateQRCode = async () => {
    try {
      const response = await api.post(`/entitlements/${entitlementId}/proof`);
      setProofToken(response.data.proof_token);
      setExpiresAt(response.data.expires_at);
      setTimeLeft(response.data.ttl_seconds);
    } catch (error) {
      console.error('Failed to generate QR code:', error);
    }
  };
  
  return (
    <View>
      {proofToken ? (
        <>
          <QRCode
            value={proofToken}
            size={250}
            backgroundColor="white"
            color="black"
          />
          <Text>Expires in: {timeLeft}s</Text>
          {timeLeft === 0 && (
            <Button title="Regenerate" onPress={generateQRCode} />
          )}
        </>
      ) : (
        <ActivityIndicator />
      )}
    </View>
  );
};
```

---

### 7.5 Error Handling

**Centralized Error Handler:**
```javascript
const handleApiError = (error) => {
  if (error.response) {
    // Server responded with error
    const status = error.response.status;
    const detail = error.response.data?.detail || 'An error occurred';
    
    switch (status) {
      case 400:
        Alert.alert('Invalid Request', detail);
        break;
      case 401:
        Alert.alert('Session Expired', 'Please login again');
        // Navigate to login
        break;
      case 403:
        Alert.alert('Access Denied', detail);
        break;
      case 404:
        Alert.alert('Not Found', detail);
        break;
      case 429:
        Alert.alert('Rate Limit', detail);
        break;
      case 500:
        Alert.alert('Server Error', 'Please try again later');
        break;
      default:
        Alert.alert('Error', detail);
    }
  } else if (error.request) {
    // Request made but no response
    Alert.alert('Network Error', 'Please check your connection');
  } else {
    // Something else happened
    Alert.alert('Error', error.message);
  }
};

// Usage
try {
  const response = await api.get('/offers/home');
  // Handle success
} catch (error) {
  handleApiError(error);
}
```

---

### 7.6 Pagination

**Implement Infinite Scroll:**
```javascript
import { FlatList } from 'react-native';
import { useState, useEffect } from 'react';

const OffersScreen = () => {
  const [offers, setOffers] = useState([]);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  
  const loadOffers = async (pageNum = 1) => {
    if (loading || !hasMore) return;
    
    setLoading(true);
    try {
      const response = await api.get('/offers/home', {
        params: { page: pageNum, page_size: 20 },
      });
      
      const newOffers = response.data.items;
      
      if (pageNum === 1) {
        setOffers(newOffers);
      } else {
        setOffers([...offers, ...newOffers]);
      }
      
      setHasMore(pageNum < response.data.total_pages);
      setPage(pageNum);
    } catch (error) {
      handleApiError(error);
    } finally {
      setLoading(false);
    }
  };
  
  useEffect(() => {
    loadOffers(1);
  }, []);
  
  const loadMore = () => {
    if (!loading && hasMore) {
      loadOffers(page + 1);
    }
  };
  
  return (
    <FlatList
      data={offers}
      renderItem={({ item }) => <OfferCard offer={item} />}
      keyExtractor={(item) => item.id}
      onEndReached={loadMore}
      onEndReachedThreshold={0.5}
      ListFooterComponent={loading && <ActivityIndicator />}
    />
  );
};
```

---

### 7.7 Caching

**Cache Categories:**
```javascript
import AsyncStorage from '@react-native-async-storage/async-storage';

const CACHE_KEY = 'categories_cache';
const CACHE_DURATION = 24 * 60 * 60 * 1000; // 24 hours

const getCategories = async () => {
  try {
    // Check cache first
    const cached = await AsyncStorage.getItem(CACHE_KEY);
    if (cached) {
      const { data, timestamp } = JSON.parse(cached);
      const age = Date.now() - timestamp;
      
      if (age < CACHE_DURATION) {
        return data;
      }
    }
    
    // Fetch from API
    const response = await api.get('/offers/categories/list');
    const categories = response.data.categories;
    
    // Update cache
    await AsyncStorage.setItem(
      CACHE_KEY,
      JSON.stringify({
        data: categories,
        timestamp: Date.now(),
      })
    );
    
    return categories;
  } catch (error) {
    handleApiError(error);
    return [];
  }
};
```

---

### 7.8 Rate Limiting

**Handle Rate Limits:**
```javascript
const [rateLimited, setRateLimited] = useState(false);
const [retryAfter, setRetryAfter] = useState(0);

const sendMessage = async (message) => {
  if (rateLimited) {
    Alert.alert('Rate Limited', `Please wait ${retryAfter} seconds`);
    return;
  }
  
  try {
    const response = await api.post('/orbit/chat', { message });
    return response.data;
  } catch (error) {
    if (error.response?.status === 429) {
      setRateLimited(true);
      
      // Parse retry-after header or use default
      const retrySeconds = error.response.headers['retry-after'] || 60;
      setRetryAfter(retrySeconds);
      
      // Start countdown
      const interval = setInterval(() => {
        setRetryAfter((prev) => {
          if (prev <= 1) {
            clearInterval(interval);
            setRateLimited(false);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    }
    handleApiError(error);
  }
};
```

---

## 8. Testing

### 8.1 Test Credentials

**Development/Staging:**
- Email: `test@university.edu`
- OTP: `123456` (dev mode only)

**Production:**
- Use real university email
- OTP sent via email

---

### 8.2 Test Merchant PIN

**Development/Staging:**
- PIN: `1234`

**Production:**
- Contact merchant for actual PIN

---

### 8.3 Postman Collection

Import the provided Postman collections:
- `StudentVerse-API.postman_collection.json` (Auth + Offers)
- `StudentVerse-Phase3-Redemption.postman_collection.json` (Entitlements)

**Environment Variables:**
```
base_url: https://svapp-backend-production.up.railway.app
access_token: (auto-populated after verify-otp)
```

---

## 9. Additional Resources

### 9.1 API Documentation
- Swagger UI: https://svapp-backend-production.up.railway.app/docs
- ReDoc: https://svapp-backend-production.up.railway.app/redoc

### 9.2 Architecture Docs
- See `docs/architecture.md` in backend repo
- See `docs/redemption-flow.md` for QR system details
- See `docs/phases.md` for development roadmap

### 9.3 Support
- Backend issues: Check `/health` endpoint
- Rate limits: Implement exponential backoff
- Errors: Log to monitoring service (Sentry, etc.)

---

## 10. Migration Checklist

### Frontend Implementation Checklist

- [ ] **Authentication**
  - [ ] Implement OTP flow (send → verify → register)
  - [ ] Store JWT token securely
  - [ ] Add Authorization header to all requests
  - [ ] Handle 401 responses (redirect to login)
  - [ ] Implement device binding (X-Device-ID header)

- [ ] **Offers**
  - [ ] Home feed with location
  - [ ] Search with filters
  - [ ] Nearby offers with map view
  - [ ] Offer detail screen
  - [ ] Category navigation
  - [ ] Infinite scroll pagination

- [ ] **Entitlements**
  - [ ] Claim offer flow
  - [ ] QR code generation with countdown
  - [ ] My offers/wallet screen
  - [ ] Savings summary display
  - [ ] Handle expired entitlements

- [ ] **Orbit AI**
  - [ ] Chat interface
  - [ ] Session management
  - [ ] Rate limit handling
  - [ ] Offer cards display
  - [ ] Mode selection (chat/find/plan)

- [ ] **Error Handling**
  - [ ] Centralized error handler
  - [ ] Network error handling
  - [ ] Rate limit UI feedback
  - [ ] Validation error display

- [ ] **Security**
  - [ ] Secure token storage
  - [ ] Device ID generation
  - [ ] Location permissions
  - [ ] HTTPS only

- [ ] **Performance**
  - [ ] Cache categories
  - [ ] Optimize image loading
  - [ ] Implement pull-to-refresh
  - [ ] Loading states

---

**Last Updated:** February 23, 2026  
**API Version:** 1.0.0  
**Backend URL:** https://svapp-backend-production.up.railway.app

