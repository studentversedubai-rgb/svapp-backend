# API Contracts - Frontend-Backend Agreement

## Overview

This document defines the API contracts between the React Native mobile app (frontend) and the FastAPI backend. These contracts ensure both teams can work in parallel with clear expectations.

---

## General API Conventions

### Base URL
```
Development: http://localhost:8000
Production:  https://api.studentverse.com
```

### API Versioning
All endpoints prefixed with `/api/v1`

### Authentication
All authenticated endpoints require:
```http
Authorization: Bearer {access_token}
```

### Response Format

**Success Response:**
```json
{
  "success": true,
  "message": "Operation successful",
  "data": { ... }
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Error message",
  "details": { ... }
}
```

### Pagination
Paginated endpoints accept:
```
?page=1&page_size=20
```

Response includes:
```json
{
  "items": [...],
  "total": 100,
  "page": 1,
  "page_size": 20,
  "total_pages": 5
}
```

---

## Authentication Endpoints

### Send OTP
```http
POST /api/v1/auth/send-otp
Content-Type: application/json

{
  "email": "student@university.edu"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "If this email is registered, an OTP has been sent"
}
```

**Errors:**
- `400`: Invalid email format
- `400`: Non-university email
- `429`: Rate limit exceeded

---

### Verify OTP
```http
POST /api/v1/auth/verify-otp
Content-Type: application/json

{
  "email": "student@university.edu",
  "otp": "123456"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Authentication successful",
  "user_id": "uuid",
  "email": "student@university.edu",
  "tokens": {
    "access_token": "jwt_token",
    "refresh_token": "refresh_token",
    "token_type": "bearer",
    "expires_in": 3600
  },
  "is_new_user": true
}
```

**Errors:**
- `401`: Invalid or expired OTP
- `429`: Too many attempts

---

### Refresh Token
```http
POST /api/v1/auth/refresh
Content-Type: application/json

{
  "refresh_token": "refresh_token"
}
```

**Response (200):**
```json
{
  "success": true,
  "access_token": "new_jwt_token",
  "token_type": "bearer",
  "expires_in": 3600
}
```

---

## User Endpoints

### Get Current User Profile
```http
GET /api/v1/users/me
Authorization: Bearer {access_token}
```

**Response (200):**
```json
{
  "id": "uuid",
  "email": "student@university.edu",
  "first_name": "John",
  "last_name": "Doe",
  "phone_number": "+971501234567",
  "university": "University of Dubai",
  "graduation_year": 2025,
  "role": "student",
  "status": "active",
  "created_at": "2026-01-01T00:00:00Z",
  "last_login": "2026-01-22T10:00:00Z"
}
```

---

### Update User Profile
```http
PATCH /api/v1/users/me
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "first_name": "John",
  "last_name": "Doe",
  "phone_number": "+971501234567",
  "university": "University of Dubai",
  "graduation_year": 2025
}
```

**Note:** Email cannot be updated (immutable)

**Response (200):**
```json
{
  "success": true,
  "message": "Profile updated successfully",
  "data": { ... }
}
```

---

## Offers Endpoints

### List Offers
```http
GET /api/v1/offers?category=food_beverage&page=1&page_size=20
Authorization: Bearer {access_token}
```

**Query Parameters:**
- `category` (optional): Filter by category
- `partner_id` (optional): Filter by partner
- `search` (optional): Search in title/description
- `page` (optional): Page number (default: 1)
- `page_size` (optional): Items per page (default: 20)

**Response (200):**
```json
{
  "items": [
    {
      "id": "uuid",
      "title": "50% Off Coffee",
      "description": "Get 50% off any coffee drink",
      "partner_id": "uuid",
      "partner_name": "Starbucks",
      "category": "food_beverage",
      "offer_type": "discount",
      "discount_value": "50%",
      "image_url": "https://...",
      "valid_from": "2026-01-01T00:00:00Z",
      "valid_until": "2026-12-31T23:59:59Z",
      "is_active": true,
      "total_claims": 150
    }
  ],
  "total": 50,
  "page": 1,
  "page_size": 20,
  "total_pages": 3
}
```

---

### Get Offer Details
```http
GET /api/v1/offers/{offer_id}
Authorization: Bearer {access_token}
```

**Response (200):**
```json
{
  "id": "uuid",
  "title": "50% Off Coffee",
  "description": "Get 50% off any coffee drink",
  "partner_id": "uuid",
  "partner_name": "Starbucks",
  "category": "food_beverage",
  "offer_type": "discount",
  "discount_value": "50%",
  "terms_conditions": "Valid on weekdays only...",
  "image_url": "https://...",
  "valid_from": "2026-01-01T00:00:00Z",
  "valid_until": "2026-12-31T23:59:59Z",
  "is_active": true,
  "total_claims": 150,
  "max_claims_per_user": 1,
  "created_at": "2026-01-01T00:00:00Z"
}
```

---

### Claim Offer
```http
POST /api/v1/offers/{offer_id}/claim
Authorization: Bearer {access_token}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Offer claimed successfully",
  "entitlement_id": "uuid",
  "offer_id": "uuid"
}
```

**Errors:**
- `400`: Already claimed
- `400`: Claim limit exceeded
- `404`: Offer not found
- `410`: Offer expired

---

## Entitlements Endpoints

### Get My Entitlements
```http
GET /api/v1/entitlements/my?state=claimed&page=1
Authorization: Bearer {access_token}
```

**Query Parameters:**
- `state` (optional): Filter by state (claimed, reserved, redeemed, etc.)
- `page`, `page_size`: Pagination

**Response (200):**
```json
{
  "items": [
    {
      "id": "uuid",
      "offer_id": "uuid",
      "offer_title": "50% Off Coffee",
      "partner_name": "Starbucks",
      "state": "claimed",
      "redemption_method": "qr_code",
      "claimed_at": "2026-01-22T10:00:00Z",
      "expires_at": "2026-12-31T23:59:59Z"
    }
  ],
  "total": 10,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

---

### Get Entitlement Details
```http
GET /api/v1/entitlements/{entitlement_id}
Authorization: Bearer {access_token}
```

**Response (200):**
```json
{
  "id": "uuid",
  "offer_id": "uuid",
  "offer_title": "50% Off Coffee",
  "offer_description": "Get 50% off any coffee drink",
  "partner_name": "Starbucks",
  "state": "claimed",
  "redemption_method": "qr_code",
  "qr_code": "base64_encoded_qr_image",
  "redemption_code": "ABC123",
  "claimed_at": "2026-01-22T10:00:00Z",
  "expires_at": "2026-12-31T23:59:59Z"
}
```

---

### Reserve Entitlement
```http
POST /api/v1/entitlements/{entitlement_id}/reserve
Authorization: Bearer {access_token}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Entitlement reserved for redemption",
  "entitlement_id": "uuid",
  "qr_code": "base64_encoded_qr_image",
  "expires_in_minutes": 15
}
```

**State Transition:** CLAIMED → RESERVED

---

## SV Orbit Endpoints

### Generate Activity Plan
```http
POST /api/v1/orbit/plans
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "intent": "date night in downtown Dubai",
  "preferences": {
    "budget": 200,
    "location": "Downtown Dubai"
  }
}
```

**Response (200):**
```json
{
  "plan_id": "uuid",
  "user_id": "uuid",
  "intent": "date night in downtown Dubai",
  "offers": [
    {
      "offer_id": "uuid",
      "title": "50% Off Dinner",
      "partner_name": "Restaurant XYZ",
      "category": "food_beverage",
      "description": "...",
      "relevance_score": 0.95,
      "reasoning": "Perfect for a romantic dinner with 50% discount"
    }
  ],
  "presentation": "Here's a perfect date night plan for you in Downtown Dubai...",
  "total_estimated_savings": 150.00,
  "created_at": "2026-01-22T10:00:00Z",
  "status": "active"
}
```

---

### Submit Plan Feedback
```http
POST /api/v1/orbit/plans/{plan_id}/feedback
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "rating": 5,
  "was_helpful": true,
  "comments": "Great suggestions!",
  "used_offers": ["offer_uuid_1", "offer_uuid_2"]
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Thank you for your feedback!"
}
```

---

## Analytics Endpoints

### Track Event
```http
POST /api/v1/analytics/track
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "event_type": "offer_view",
  "metadata": {
    "offer_id": "uuid",
    "source": "home_screen"
  }
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Event tracked successfully"
}
```

---

### Get User Statistics
```http
GET /api/v1/analytics/user-stats
Authorization: Bearer {access_token}
```

**Response (200):**
```json
{
  "user_id": "uuid",
  "total_offers_viewed": 50,
  "total_offers_claimed": 10,
  "total_entitlements_redeemed": 5,
  "total_savings": 250.00,
  "member_since": "2026-01-01T00:00:00Z",
  "last_activity": "2026-01-22T10:00:00Z"
}
```

---

## Error Codes Reference

| Code | Meaning | Common Causes |
|------|---------|---------------|
| 400 | Bad Request | Invalid input, validation error |
| 401 | Unauthorized | Invalid/expired token, invalid OTP |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource doesn't exist |
| 409 | Conflict | Duplicate resource, state conflict |
| 410 | Gone | Resource expired |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server-side error |
| 503 | Service Unavailable | Feature disabled (e.g., SV Pay) |

---

## Frontend Implementation Notes

### Token Management
```javascript
// Store tokens securely
await SecureStore.setItemAsync('access_token', tokens.access_token);
await SecureStore.setItemAsync('refresh_token', tokens.refresh_token);

// Add to all requests
const api = axios.create({
  baseURL: 'https://api.studentverse.com/api/v1',
  headers: {
    'Authorization': `Bearer ${await SecureStore.getItemAsync('access_token')}`
  }
});

// Auto-refresh on 401
api.interceptors.response.use(
  response => response,
  async error => {
    if (error.response?.status === 401) {
      // Attempt token refresh
      const refreshToken = await SecureStore.getItemAsync('refresh_token');
      const response = await axios.post('/auth/refresh', { refresh_token: refreshToken });
      await SecureStore.setItemAsync('access_token', response.data.access_token);
      // Retry original request
      return api.request(error.config);
    }
    return Promise.reject(error);
  }
);
```

### Error Handling
```javascript
try {
  const response = await api.get('/offers');
  setOffers(response.data.items);
} catch (error) {
  if (error.response?.status === 401) {
    // Redirect to login
    navigation.navigate('Login');
  } else {
    Alert.alert('Error', error.response?.data?.error || 'Something went wrong');
  }
}
```

---

**Last Updated**: 2026-01-22
