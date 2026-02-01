# Testing Guide: Phase 1 + Phase 2

## Overview
This guide walks you through testing the complete backend from authentication to offer browsing.

---

## Prerequisites

### 1. Install Dependencies
```bash
# Activate virtual environment
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Set Up Environment Variables
Create `.env` file with your credentials:
```bash
# Supabase
SUPABASE_URL=your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-key

# Redis (optional for testing)
REDIS_URL=redis://localhost:6379

# JWT
JWT_SECRET=your-jwt-secret

# Email domains
ALLOWED_EMAIL_DOMAINS=student.university.edu,edu.university.ae
```

### 3. Set Up Test Database
You'll need to create the database tables in Supabase:

```sql
-- Create users table (Phase 1)
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email VARCHAR UNIQUE NOT NULL,
  first_name VARCHAR,
  last_name VARCHAR,
  phone_number VARCHAR,
  university VARCHAR,
  graduation_year INTEGER,
  role VARCHAR DEFAULT 'student',
  status VARCHAR DEFAULT 'active',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  last_login TIMESTAMP WITH TIME ZONE
);

-- Create merchants table (Phase 2)
CREATE TABLE merchants (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name VARCHAR NOT NULL,
  description TEXT,
  logo_url VARCHAR,
  latitude FLOAT,
  longitude FLOAT,
  address TEXT,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE
);

-- Create categories table (Phase 2)
CREATE TABLE categories (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name VARCHAR UNIQUE NOT NULL,
  slug VARCHAR UNIQUE NOT NULL,
  description TEXT,
  icon_url VARCHAR,
  sort_order INTEGER DEFAULT 0,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create offers table (Phase 2)
CREATE TABLE offers (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  merchant_id UUID REFERENCES merchants(id),
  category_id UUID REFERENCES categories(id),
  title VARCHAR NOT NULL,
  description TEXT NOT NULL,
  terms_conditions TEXT,
  offer_type VARCHAR NOT NULL,
  discount_value VARCHAR,
  original_price FLOAT,
  discounted_price FLOAT,
  image_url VARCHAR,
  images TEXT[],
  valid_from TIMESTAMP WITH TIME ZONE NOT NULL,
  valid_until TIMESTAMP WITH TIME ZONE NOT NULL,
  time_valid_from TIME,
  time_valid_until TIME,
  valid_days_of_week INTEGER[],
  max_claims_per_user INTEGER,
  total_claims INTEGER DEFAULT 0,
  max_total_claims INTEGER,
  is_active BOOLEAN DEFAULT TRUE,
  is_featured BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE
);

-- Create indexes for performance
CREATE INDEX idx_offers_merchant_id ON offers(merchant_id);
CREATE INDEX idx_offers_category_id ON offers(category_id);
CREATE INDEX idx_offers_is_active ON offers(is_active);
CREATE INDEX idx_offers_valid_from ON offers(valid_from);
CREATE INDEX idx_offers_valid_until ON offers(valid_until);
CREATE INDEX idx_offers_created_at ON offers(created_at);
CREATE INDEX idx_merchants_is_active ON merchants(is_active);
```

### 4. Insert Test Data
```sql
-- Insert test merchant
INSERT INTO merchants (id, name, description, logo_url, latitude, longitude, address, is_active)
VALUES (
  '550e8400-e29b-41d4-a716-446655440000',
  'Starbucks Dubai Mall',
  'Premium coffee shop',
  'https://example.com/starbucks-logo.png',
  25.1972,
  55.2744,
  'Dubai Mall, Downtown Dubai',
  TRUE
);

-- Insert test category
INSERT INTO categories (id, name, slug, description, sort_order, is_active)
VALUES (
  '660e8400-e29b-41d4-a716-446655440000',
  'Food & Beverage',
  'food-beverage',
  'Restaurants, cafes, and food outlets',
  1,
  TRUE
);

-- Insert test offer (active, no time/day restrictions)
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
  is_active,
  is_featured
)
VALUES (
  '770e8400-e29b-41d4-a716-446655440000',
  '550e8400-e29b-41d4-a716-446655440000',
  '660e8400-e29b-41d4-a716-446655440000',
  '50% Off Any Coffee',
  'Get 50% discount on any coffee drink of your choice',
  'Valid for students only. Cannot be combined with other offers.',
  'discount',
  '50%',
  20.0,
  10.0,
  'https://example.com/coffee-offer.jpg',
  NOW() - INTERVAL '1 day',
  NOW() + INTERVAL '30 days',
  TRUE,
  TRUE
);

-- Insert offer with time restriction (Happy Hour)
INSERT INTO offers (
  id,
  merchant_id,
  category_id,
  title,
  description,
  offer_type,
  discount_value,
  valid_from,
  valid_until,
  time_valid_from,
  time_valid_until,
  is_active
)
VALUES (
  '880e8400-e29b-41d4-a716-446655440000',
  '550e8400-e29b-41d4-a716-446655440000',
  '660e8400-e29b-41d4-a716-446655440000',
  'Happy Hour Special',
  'Special discount during happy hours',
  'discount',
  '30%',
  NOW() - INTERVAL '1 day',
  NOW() + INTERVAL '30 days',
  '17:00:00',
  '19:00:00',
  TRUE
);

-- Insert offer with day restriction (Weekdays only)
INSERT INTO offers (
  id,
  merchant_id,
  category_id,
  title,
  description,
  offer_type,
  discount_value,
  valid_from,
  valid_until,
  valid_days_of_week,
  is_active
)
VALUES (
  '990e8400-e29b-41d4-a716-446655440000',
  '550e8400-e29b-41d4-a716-446655440000',
  '660e8400-e29b-41d4-a716-446655440000',
  'Weekday Lunch Special',
  'Special offer for weekday lunches',
  'discount',
  '25%',
  NOW() - INTERVAL '1 day',
  NOW() + INTERVAL '30 days',
  ARRAY[0, 1, 2, 3, 4],
  TRUE
);
```

---

## Start the Server

```bash
# Make sure you're in the project directory
cd c:\Users\msina\OneDrive\Desktop\sv\sv-backend

# Activate virtual environment
venv\Scripts\activate

# Run the server
uvicorn app.main:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Startup complete
```

---

## Testing with Postman/Thunder Client

### Step 1: Health Check
**Request:**
```
GET http://localhost:8000/
```

**Expected Response:**
```json
{
  "message": "StudentVerse API",
  "version": "1.0.0",
  "docs": "/docs",
  "health": "/health"
}
```

---

### Step 2: View API Documentation
Open in browser:
```
http://localhost:8000/docs
```

You should see Swagger UI with all endpoints.

---

## PHASE 1 TESTING: Authentication

### Step 3: Send OTP (Register/Login)
**Request:**
```
POST http://localhost:8000/auth/send-otp
Content-Type: application/json

{
  "email": "student@university.edu"
}
```

**Expected Response:**
```json
{
  "success": true,
  "message": "If this email is registered, an OTP has been sent"
}
```

**Note:** Check your email for the OTP code. If Supabase email is not configured, check Supabase dashboard for the OTP.

---

### Step 4: Verify OTP
**Request:**
```
POST http://localhost:8000/auth/verify-otp
Content-Type: application/json

{
  "email": "student@university.edu",
  "otp": "123456"
}
```

**Expected Response:**
```json
{
  "success": true,
  "message": "Authentication successful",
  "user_id": "uuid-here",
  "email": "student@university.edu",
  "tokens": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "refresh-token-here",
    "token_type": "bearer",
    "expires_in": 3600
  },
  "is_new_user": true
}
```

**IMPORTANT:** Copy the `access_token` - you'll need it for all subsequent requests!

---

### Step 5: Get Current User Profile
**Request:**
```
GET http://localhost:8000/users/me
Authorization: Bearer YOUR_ACCESS_TOKEN_HERE
```

**Expected Response:**
```json
{
  "id": "uuid-here",
  "email": "student@university.edu",
  "first_name": null,
  "last_name": null,
  "phone_number": null,
  "university": null,
  "graduation_year": null,
  "role": "student",
  "status": "active",
  "created_at": "2026-01-26T15:00:00Z",
  "last_login": "2026-01-26T15:30:00Z"
}
```

---

### Step 6: Update User Profile
**Request:**
```
PATCH http://localhost:8000/users/me
Authorization: Bearer YOUR_ACCESS_TOKEN_HERE
Content-Type: application/json

{
  "first_name": "John",
  "last_name": "Doe",
  "phone_number": "+971501234567",
  "university": "University of Dubai",
  "graduation_year": 2025
}
```

**Expected Response:**
```json
{
  "success": true,
  "message": "Profile updated successfully",
  "data": {
    "id": "uuid-here",
    "email": "student@university.edu",
    "first_name": "John",
    "last_name": "Doe",
    "phone_number": "+971501234567",
    "university": "University of Dubai",
    "graduation_year": 2025,
    "role": "student",
    "status": "active"
  }
}
```

---

## PHASE 2 TESTING: Offers

**IMPORTANT:** All Phase 2 endpoints require the `Authorization` header with your access token!

### Step 7: Get Categories
**Request:**
```
GET http://localhost:8000/offers/categories/list
Authorization: Bearer YOUR_ACCESS_TOKEN_HERE
```

**Expected Response:**
```json
{
  "categories": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440000",
      "name": "Food & Beverage",
      "slug": "food-beverage",
      "description": "Restaurants, cafes, and food outlets",
      "icon_url": null,
      "sort_order": 1
    }
  ]
}
```

---

### Step 8: Get Home Feed (Without Location)
**Request:**
```
GET http://localhost:8000/offers/home?page=1&page_size=20
Authorization: Bearer YOUR_ACCESS_TOKEN_HERE
```

**Expected Response:**
```json
{
  "items": [
    {
      "id": "770e8400-e29b-41d4-a716-446655440000",
      "title": "50% Off Any Coffee",
      "description": "Get 50% discount on any coffee drink of your choice",
      "merchant": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "Starbucks Dubai Mall",
        "logo_url": "https://example.com/starbucks-logo.png",
        "latitude": 25.1972,
        "longitude": 55.2744
      },
      "category": {
        "id": "660e8400-e29b-41d4-a716-446655440000",
        "name": "Food & Beverage",
        "slug": "food-beverage"
      },
      "offer_type": "discount",
      "discount_value": "50%",
      "original_price": 20.0,
      "discounted_price": 10.0,
      "image_url": "https://example.com/coffee-offer.jpg",
      "valid_from": "2026-01-25T00:00:00Z",
      "valid_until": "2026-02-25T00:00:00Z",
      "distance_km": null,
      "is_featured": true,
      "created_at": "2026-01-26T00:00:00Z"
    }
  ],
  "total": 3,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

---

### Step 9: Get Home Feed (With Location)
**Request:**
```
GET http://localhost:8000/offers/home?latitude=25.2048&longitude=55.2708&page=1&page_size=20
Authorization: Bearer YOUR_ACCESS_TOKEN_HERE
```

**Expected Response:**
```json
{
  "items": [
    {
      "id": "770e8400-e29b-41d4-a716-446655440000",
      "title": "50% Off Any Coffee",
      "description": "Get 50% discount on any coffee drink of your choice",
      "merchant": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "Starbucks Dubai Mall",
        "logo_url": "https://example.com/starbucks-logo.png",
        "latitude": 25.1972,
        "longitude": 55.2744
      },
      "category": {...},
      "offer_type": "discount",
      "discount_value": "50%",
      "distance_km": 1.2,
      "is_featured": true,
      "created_at": "2026-01-26T00:00:00Z"
    }
  ],
  "total": 3,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

**Note:** Items are now sorted by `distance_km` (nearest first)!

---

### Step 10: Search Offers
**Request:**
```
GET http://localhost:8000/offers/search?query=coffee&page=1&page_size=20
Authorization: Bearer YOUR_ACCESS_TOKEN_HERE
```

**Expected Response:**
```json
{
  "items": [
    {
      "id": "770e8400-e29b-41d4-a716-446655440000",
      "title": "50% Off Any Coffee",
      "description": "Get 50% discount on any coffee drink of your choice",
      ...
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

---

### Step 11: Search with Category Filter
**Request:**
```
GET http://localhost:8000/offers/search?category_id=660e8400-e29b-41d4-a716-446655440000&page=1&page_size=20
Authorization: Bearer YOUR_ACCESS_TOKEN_HERE
```

---

### Step 12: Get Nearby Offers
**Request:**
```
GET http://localhost:8000/offers/nearby?latitude=25.2048&longitude=55.2708&radius_km=10&page=1&page_size=20
Authorization: Bearer YOUR_ACCESS_TOKEN_HERE
```

**Expected Response:**
```json
{
  "items": [
    {
      "id": "770e8400-e29b-41d4-a716-446655440000",
      "title": "50% Off Any Coffee",
      "distance_km": 1.2,
      ...
    }
  ],
  "total": 3,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

**Note:** Results sorted by distance (nearest first)!

---

### Step 13: Get Offer Details
**Request:**
```
GET http://localhost:8000/offers/770e8400-e29b-41d4-a716-446655440000
Authorization: Bearer YOUR_ACCESS_TOKEN_HERE
```

**Expected Response:**
```json
{
  "id": "770e8400-e29b-41d4-a716-446655440000",
  "title": "50% Off Any Coffee",
  "description": "Get 50% discount on any coffee drink of your choice",
  "terms_conditions": "Valid for students only. Cannot be combined with other offers.",
  "merchant": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Starbucks Dubai Mall",
    "description": "Premium coffee shop",
    "logo_url": "https://example.com/starbucks-logo.png",
    "address": "Dubai Mall, Downtown Dubai",
    "latitude": 25.1972,
    "longitude": 55.2744
  },
  "category": {...},
  "offer_type": "discount",
  "discount_value": "50%",
  "original_price": 20.0,
  "discounted_price": 10.0,
  "image_url": "https://example.com/coffee-offer.jpg",
  "images": null,
  "valid_from": "2026-01-25T00:00:00Z",
  "valid_until": "2026-02-25T00:00:00Z",
  "time_valid_from": null,
  "time_valid_until": null,
  "valid_days_of_week": null,
  "max_claims_per_user": null,
  "total_claims": 0,
  "max_total_claims": null,
  "is_featured": true,
  "distance_km": null,
  "created_at": "2026-01-26T00:00:00Z",
  "updated_at": null
}
```

---

## Error Testing

### Test 1: Missing Authorization
**Request:**
```
GET http://localhost:8000/offers/home
```

**Expected Response:** `401 Unauthorized`
```json
{
  "detail": "Not authenticated"
}
```

---

### Test 2: Invalid Coordinates
**Request:**
```
GET http://localhost:8000/offers/home?latitude=100&longitude=55.2708
Authorization: Bearer YOUR_ACCESS_TOKEN_HERE
```

**Expected Response:** `422 Unprocessable Entity`

---

### Test 3: Missing Location Pair
**Request:**
```
GET http://localhost:8000/offers/home?latitude=25.2048
Authorization: Bearer YOUR_ACCESS_TOKEN_HERE
```

**Expected Response:** `400 Bad Request`
```json
{
  "detail": "Both latitude and longitude must be provided together"
}
```

---

### Test 4: Invalid Offer ID
**Request:**
```
GET http://localhost:8000/offers/non-existent-id
Authorization: Bearer YOUR_ACCESS_TOKEN_HERE
```

**Expected Response:** `404 Not Found`
```json
{
  "detail": "Offer not found"
}
```

---

## Running Automated Tests

### Unit Tests
```bash
# Run all unit tests
pytest tests/unit/ -v

# Run specific test file
pytest tests/unit/test_offer_service.py -v

# Run with coverage
pytest tests/unit/ --cov=app.modules.offers --cov-report=html
```

### Integration Tests
```bash
# Run all integration tests
pytest tests/integration/ -v

# Run specific test file
pytest tests/integration/test_offers_endpoints.py -v
```

### All Tests
```bash
# Run everything
pytest -v

# With coverage
pytest --cov=app --cov-report=html
```

---

## Troubleshooting

### Issue: "Database connection error"
**Solution:** Check your `.env` file has correct Supabase credentials

### Issue: "Token expired"
**Solution:** Get a new token by calling `/auth/verify-otp` again

### Issue: "No offers returned"
**Solution:** Make sure you inserted test data in Supabase

### Issue: "Module not found"
**Solution:** Make sure virtual environment is activated and dependencies installed

### Issue: "Redis connection failed"
**Solution:** Redis is optional for testing. Comment out Redis code in `app/main.py` if not using it.

---

## Success Checklist

- [ ] Server starts without errors
- [ ] Can access `/docs` endpoint
- [ ] Can send OTP to email
- [ ] Can verify OTP and get access token
- [ ] Can get user profile with token
- [ ] Can update user profile
- [ ] Can get categories list
- [ ] Can get home feed without location
- [ ] Can get home feed with location (sorted by distance)
- [ ] Can search offers by keyword
- [ ] Can filter by category
- [ ] Can get nearby offers
- [ ] Can get offer details
- [ ] Authentication errors work correctly (401)
- [ ] Validation errors work correctly (400/422)
- [ ] Not found errors work correctly (404)

---

**If all tests pass, you're ready to push to GitHub! 🎉**
