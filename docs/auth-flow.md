# Mobile Authentication Flow

## Overview

StudentVerse uses **OTP-based authentication** with **Supabase Auth** for the mobile application. This document explains the complete authentication flow for iOS and Android apps.

## Key Principles

1. **No Password Storage**: Backend never stores passwords - Supabase handles this
2. **Immutable Email**: University email cannot be changed after registration
3. **Persistent Login**: JWT refresh tokens for seamless mobile experience
4. **University Email Only**: Only verified university domains allowed

## Authentication Flow

### 1. Initial Registration / Login

```
┌─────────┐                 ┌─────────┐                 ┌──────────┐
│  Mobile │                 │ Backend │                 │ Supabase │
│   App   │                 │   API   │                 │   Auth   │
└────┬────┘                 └────┬────┘                 └────┬─────┘
     │                           │                           │
     │ POST /auth/send-otp       │                           │
     │ {email: "user@uni.edu"}   │                           │
     ├──────────────────────────>│                           │
     │                           │                           │
     │                           │ Validate university email │
     │                           │ Check rate limiting       │
     │                           │                           │
     │                           │ Generate OTP              │
     │                           ├──────────────────────────>│
     │                           │                           │
     │                           │ OTP sent to email         │
     │                           │<──────────────────────────┤
     │                           │                           │
     │ {success: true}           │                           │
     │<──────────────────────────┤                           │
     │                           │                           │
     │                           │                           │
     │ POST /auth/verify-otp     │                           │
     │ {email, otp: "123456"}    │                           │
     ├──────────────────────────>│                           │
     │                           │                           │
     │                           │ Verify OTP                │
     │                           ├──────────────────────────>│
     │                           │                           │
     │                           │ JWT tokens                │
     │                           │<──────────────────────────┤
     │                           │                           │
     │                           │ Create/update user record │
     │                           │ (if new user)             │
     │                           │                           │
     │ {access_token,            │                           │
     │  refresh_token,           │                           │
     │  user_id, email}          │                           │
     │<──────────────────────────┤                           │
     │                           │                           │
     │ Store tokens securely     │                           │
     │ (Keychain/Keystore)       │                           │
     │                           │                           │
```

### 2. Authenticated Requests

```
┌─────────┐                 ┌─────────┐
│  Mobile │                 │ Backend │
│   App   │                 │   API   │
└────┬────┘                 └────┬────┘
     │                           │
     │ GET /offers               │
     │ Authorization: Bearer     │
     │ {access_token}            │
     ├──────────────────────────>│
     │                           │
     │                           │ Verify JWT signature
     │                           │ Extract user_id
     │                           │ Check expiration
     │                           │
     │ {offers: [...]}           │
     │<──────────────────────────┤
     │                           │
```

### 3. Token Refresh

```
┌─────────┐                 ┌─────────┐                 ┌──────────┐
│  Mobile │                 │ Backend │                 │ Supabase │
│   App   │                 │   API   │                 │   Auth   │
└────┬────┘                 └────┬────┘                 └────┬─────┘
     │                           │                           │
     │ Access token expired      │                           │
     │                           │                           │
     │ POST /auth/refresh        │                           │
     │ {refresh_token}           │                           │
     ├──────────────────────────>│                           │
     │                           │                           │
     │                           │ Validate refresh token    │
     │                           ├──────────────────────────>│
     │                           │                           │
     │                           │ New access token          │
     │                           │<──────────────────────────┤
     │                           │                           │
     │ {access_token,            │                           │
     │  expires_in}              │                           │
     │<──────────────────────────┤                           │
     │                           │                           │
     │ Update stored token       │                           │
     │                           │                           │
```

### 4. Logout

```
┌─────────┐                 ┌─────────┐                 ┌──────────┐
│  Mobile │                 │ Backend │                 │ Supabase │
│   App   │                 │   API   │                 │   Auth   │
└────┬────┘                 └────┬────┘                 └────┬─────┘
     │                           │                           │
     │ POST /auth/logout         │                           │
     │ {refresh_token}           │                           │
     ├──────────────────────────>│                           │
     │                           │                           │
     │                           │ Invalidate refresh token  │
     │                           ├──────────────────────────>│
     │                           │                           │
     │                           │ Success                   │
     │                           │<──────────────────────────┤
     │                           │                           │
     │ {success: true}           │                           │
     │<──────────────────────────┤                           │
     │                           │                           │
     │ Clear stored tokens       │                           │
     │                           │                           │
```

## Mobile App Implementation

### Token Storage

**iOS (Swift)**
```swift
// Store in Keychain
let keychain = KeychainSwift()
keychain.set(accessToken, forKey: "access_token")
keychain.set(refreshToken, forKey: "refresh_token")
```

**Android (Kotlin)**
```kotlin
// Store in EncryptedSharedPreferences
val sharedPreferences = EncryptedSharedPreferences.create(...)
sharedPreferences.edit()
    .putString("access_token", accessToken)
    .putString("refresh_token", refreshToken)
    .apply()
```

### Automatic Token Refresh

Mobile app should:
1. Intercept API responses with 401 Unauthorized
2. Attempt token refresh using refresh token
3. Retry original request with new access token
4. If refresh fails, redirect to login

### Session Persistence

- Store tokens securely on device
- Check token validity on app launch
- Auto-refresh if expired but refresh token valid
- Redirect to login only if refresh token invalid

## Security Considerations

### Email Validation
- Only university email domains allowed
- Configured in `ALLOWED_EMAIL_DOMAINS` environment variable
- Validated on both send-OTP and verify-OTP

### Rate Limiting
- OTP requests limited per email (e.g., 3 per hour)
- Stored in Redis with TTL
- Prevents spam and abuse

### OTP Security
- 6-digit numeric code
- 10-minute expiration
- Single-use only
- Stored in Redis, deleted after verification

### JWT Security
- Signed by Supabase with secret key
- Backend verifies signature on each request
- Short expiration for access tokens (e.g., 1 hour)
- Longer expiration for refresh tokens (e.g., 30 days)

### Email Immutability
- Email set during first registration
- Cannot be changed via API
- Ensures consistent user identity

## Error Handling

### Common Error Scenarios

| Scenario | HTTP Status | Response |
|----------|-------------|----------|
| Invalid email format | 400 | `{"error": "Invalid email format"}` |
| Non-university email | 400 | `{"error": "Only university emails allowed"}` |
| Rate limit exceeded | 429 | `{"error": "Too many requests"}` |
| Invalid OTP | 401 | `{"error": "Invalid or expired OTP"}` |
| Expired access token | 401 | `{"error": "Token expired"}` |
| Invalid refresh token | 401 | `{"error": "Invalid refresh token"}` |

### Mobile App Error Handling

```javascript
// React Native example
try {
  const response = await api.post('/auth/verify-otp', {
    email,
    otp
  });
  
  // Store tokens
  await SecureStore.setItemAsync('access_token', response.data.tokens.access_token);
  await SecureStore.setItemAsync('refresh_token', response.data.tokens.refresh_token);
  
  // Navigate to app
  navigation.navigate('Home');
  
} catch (error) {
  if (error.response?.status === 401) {
    Alert.alert('Error', 'Invalid OTP. Please try again.');
  } else if (error.response?.status === 429) {
    Alert.alert('Error', 'Too many attempts. Please try again later.');
  } else {
    Alert.alert('Error', 'Something went wrong. Please try again.');
  }
}
```

## Backend Implementation Notes

### Dependencies
- `app/core/security.py`: JWT verification
- `app/modules/auth/service.py`: OTP generation and verification
- `app/modules/users/service.py`: User creation and updates

### Environment Variables
```bash
SUPABASE_URL=your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-key
JWT_SECRET=your-jwt-secret
ALLOWED_EMAIL_DOMAINS=student.university.edu,edu.university.ae
```

### Database Schema
```sql
-- Users table (simplified)
CREATE TABLE users (
  id UUID PRIMARY KEY,              -- From Supabase Auth
  email VARCHAR UNIQUE NOT NULL,    -- Immutable
  first_name VARCHAR,
  last_name VARCHAR,
  role VARCHAR DEFAULT 'student',
  created_at TIMESTAMP DEFAULT NOW(),
  last_login TIMESTAMP
);
```

## Testing Authentication

### Manual Testing with Postman

1. **Send OTP**
```http
POST /api/v1/auth/send-otp
Content-Type: application/json

{
  "email": "student@university.edu"
}
```

2. **Verify OTP**
```http
POST /api/v1/auth/verify-otp
Content-Type: application/json

{
  "email": "student@university.edu",
  "otp": "123456"
}
```

3. **Use Access Token**
```http
GET /api/v1/users/me
Authorization: Bearer {access_token}
```

4. **Refresh Token**
```http
POST /api/v1/auth/refresh
Content-Type: application/json

{
  "refresh_token": "{refresh_token}"
}
```

---

**Last Updated**: 2026-01-22
