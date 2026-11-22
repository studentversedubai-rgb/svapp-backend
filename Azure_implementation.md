# Microsoft OAuth Authentication Migration — Backend Implementation Plan

Replace the OTP-based sign-up and forgot-password flows with Microsoft Azure OAuth via Supabase, while preserving the existing email+password login for all current and future users.

## Scope

- **Backend:** Full implementation (this plan covers all code changes)
- **Frontend:** Separate handoff document will be created for the frontend team — no frontend code changes in this plan

## Background

The current sign-up flow uses email OTP (via Postmark) to verify university emails. University mail gateways are silently blocking/quarantining these OTPs, causing sign-up failures. Microsoft OAuth solves this by using the university's own identity system — if a student can sign into their Microsoft university account, that's proof they own the email.

**Key constraint:** The app is live with existing users. Login via email+password must remain untouched. Changes go directly to `main`. No room for error.

---

## Existing User Safety Guarantee

> [!IMPORTANT]
> **Zero impact on existing users.** Here is exactly why:
>
> 1. **`public.users` table** — NO schema changes, NO data changes. Every existing row stays exactly as-is.
> 2. **Supabase Auth users** — NOT touched. Users created via OTP sign-up have email+password credentials in Supabase Auth. Those credentials are completely independent of the Azure provider. Both providers coexist in Supabase — they don't interfere.
> 3. **`POST /auth/login`** — Code is IDENTICAL. Same email+password flow via `supabase.auth.sign_in_with_password()`. No modifications.
> 4. **`POST /auth/register`** — Code is IDENTICAL. Still called after sign-up verification to set password and profile.
> 5. **`POST /auth/forgot-password/reset`** — Code is IDENTICAL. Still resets password via admin API.
> 6. **All other endpoints** (`/auth/me`, `/auth/logout`, `/auth/profile`, `/auth/account`, all offer/entitlement/merchant/ticket/payment endpoints) — ZERO changes.
> 7. **OTP endpoints remain** — `send-otp`, `verify-otp`, `forgot-password/send-otp`, `forgot-password/verify-otp` stay on the backend untouched as rollback safety net.

---

## Proposed Changes

### Database: One New Table

> [!NOTE]
> Single table `university_domains` — simple, flat, and sufficient. No need for a separate institutions table since the university name and domain can live together.

#### [NEW] `migrations/versions/add_university_domains_table.sql`

```sql
CREATE TABLE IF NOT EXISTS public.university_domains (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  university_name text NOT NULL,
  domain text NOT NULL,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Ensure exact-match domain lookups are fast and unique
CREATE UNIQUE INDEX IF NOT EXISTS idx_university_domains_domain_lower
  ON public.university_domains (lower(domain));

-- Index for listing active universities
CREATE INDEX IF NOT EXISTS idx_university_domains_active
  ON public.university_domains (is_active) WHERE is_active = true;
```

**Runtime acceptance query:**
```sql
SELECT university_name FROM public.university_domains
WHERE lower(domain) = lower(:user_email_domain)
  AND is_active = true;
```

If it returns a row → domain is accepted. If empty → rejected.

#### [NEW] `scripts/seed_university_domains.py`

Idempotent Python script that inserts/updates rows from a seed data file. Uses `ON CONFLICT (lower(domain)) DO UPDATE` for safe re-runs.

#### [NEW] `scripts/university_domains_seed.json`

Machine-readable seed data. You will provide the exact list of university names + domains. Example format:

```json
[
  {"university_name": "American University of Sharjah (AUS)", "domain": "aus.edu"},
  {"university_name": "University of Wollongong in Dubai (UOWD)", "domain": "uowmail.edu.au"},
  {"university_name": "Zayed University (ZU)", "domain": "zu.ac.ae"}
]
```

> [!IMPORTANT]
> **Action needed from you:** Provide the full list of university names and their exact student email domains before I build the seed file.

---

### Backend Auth Module Changes

All changes are **additive**. Existing code is not modified — only new methods, new routes, and new schemas are added.

---

#### [MODIFY] [schemas.py](file:///c:/Users/msina/OneDrive/Desktop/sv/app/backend/svapp-backend/app/modules/auth/schemas.py)

**Add** new Pydantic models (all existing schemas stay untouched):

```python
class InstitutionItem(BaseModel):
    """Single university for the institutions list"""
    university_name: str
    domain: str

class InstitutionsListResponse(BaseModel):
    """Response for GET /auth/institutions"""
    ok: bool = True
    data: list[InstitutionItem]

class MicrosoftVerifyRequest(BaseModel):
    """Empty body — bearer token in Authorization header is all we need"""
    model_config = ConfigDict(extra='forbid')

class MicrosoftSignupVerifyResponse(BaseModel):
    """Response for POST /auth/signup/verify-microsoft"""
    ok: bool = True
    data: dict  # {email, university_name, is_new_user, access_token, token_type}

class MicrosoftRecoveryVerifyResponse(BaseModel):
    """Response for POST /auth/forgot-password/verify-microsoft"""
    ok: bool = True
    data: dict  # {email, reset_token}
```

---

#### [MODIFY] [service.py](file:///c:/Users/msina/OneDrive/Desktop/sv/app/backend/svapp-backend/app/modules/auth/service.py)

**Add** three new methods to `AuthService` (all existing methods remain untouched):

##### 1. `list_verified_institutions()`

```
- Queries: SELECT university_name, domain FROM university_domains WHERE is_active = true ORDER BY university_name
- Returns: list of {university_name, domain}
- Used by: GET /auth/institutions
```

##### 2. `verify_microsoft_signup(access_token: str)`

This is the core new method. It replaces what `verify_otp()` does for sign-up, but uses the Azure OAuth token as identity proof instead of a 6-digit code.

**Step-by-step logic:**

```
1. Validate Azure token
   - Call create_fresh_supabase_client()
   - Use fresh_client.auth.get_user(access_token) to validate the token
   - If invalid/expired → 401

2. Extract and validate provider
   - Get user.app_metadata or user.identities
   - Confirm provider is "azure"
   - If not azure → 400 "Invalid authentication provider"

3. Extract and normalize email
   - email = auth_user.email (from Supabase, NOT from request body)
   - Normalize: email.lower().strip()
   - Extract domain: email.split("@")[1]

4. Whitelist domain check (BLOCKING — not a warning like current OTP flow)
   - Query: university_domains WHERE lower(domain) = lower(extracted_domain) AND is_active = true
   - If not found → 400 "Your university is not supported yet"
   - If found → store university_name for response

5. Check existing account
   - Query: public.users WHERE email = normalized_email
   - If exists → 409 "Account already exists. Please log in."

6. Create Supabase Auth user + public.users row
   (Same pattern as current verify_otp lines 111-161)
   - Generate temp password: secrets.token_urlsafe(32)
   - Create auth user: auth_client.auth.sign_up({email, password: temp})
   - Insert public.users: {id, email, account_type: "free"}
   - On failure: rollback auth user

7. Return response
   {
     "email": normalized_email,
     "university_name": matched_university,
     "is_new_user": true,
     "access_token": auth_response.session.access_token,
     "token_type": "bearer"
   }
```

##### 3. `verify_microsoft_recovery(access_token: str)`

For forgot-password flow. Same Azure token validation, but confirms the user EXISTS (opposite of signup).

**Step-by-step logic:**

```
1. Validate Azure token (same as signup step 1)
2. Validate provider is azure (same as signup step 2)
3. Extract and normalize email (same as signup step 3)
4. Whitelist domain check (same as signup step 4)

5. Check account exists
   - Query: public.users WHERE email = normalized_email
   - If NOT found → 404 "No account found with this email"
   - If found → get user_id

6. Issue reset token
   (Same pattern as current forgot_password_verify_otp lines 194-199)
   - Generate: reset_token = str(uuid.uuid4())
   - Store in Redis: sv:app:auth:reset_token:{email} → reset_token, TTL 600s

7. Return response
   {
     "email": normalized_email,
     "reset_token": reset_token
   }
```

**What stays untouched in service.py:**
- `send_otp()` — remains for rollback
- `verify_otp()` — remains for rollback
- `complete_registration()` — still called by frontend after Microsoft verification
- `login()` — identical
- `forgot_password_send_otp()` — remains for rollback
- `forgot_password_verify_otp()` — remains for rollback
- `forgot_password_reset()` — still called by frontend after Microsoft recovery
- `update_profile()`, `get_user_analytics()`, `logout_user()`, `delete_account()` — identical

---

#### [MODIFY] [router.py](file:///c:/Users/msina/OneDrive/Desktop/sv/app/backend/svapp-backend/app/modules/auth/router.py)

**Add** three new routes (all existing routes remain untouched):

##### `GET /auth/institutions`
```python
@router.get("/institutions")
async def list_institutions():
    """Return list of supported universities for frontend dropdown."""
    result = await auth_service.list_verified_institutions()
    return {"ok": True, "data": result}
```
- Public endpoint (no auth required)
- Returns the university list from `university_domains` table
- Frontend uses this instead of hardcoded `constants/universities.ts`

##### `POST /auth/signup/verify-microsoft`
```python
@router.post("/signup/verify-microsoft")
async def verify_microsoft_signup(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())
):
    """
    Verify Microsoft Azure OAuth session for new user sign-up.
    
    Expects: Bearer token from Supabase Azure OAuth session.
    Returns: verified email, university name, access token for registration.
    """
    result = await auth_service.verify_microsoft_signup(credentials.credentials)
    return {"ok": True, "data": result}
```
- Bearer token is the Supabase Azure OAuth session token
- No request body — email comes from the token, not from the client

##### `POST /auth/forgot-password/verify-microsoft`
```python
@router.post("/forgot-password/verify-microsoft")
async def verify_microsoft_recovery(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())
):
    """
    Verify Microsoft Azure OAuth session for password recovery.
    
    Expects: Bearer token from Supabase Azure OAuth session.
    Returns: email and short-lived reset token.
    """
    result = await auth_service.verify_microsoft_recovery(credentials.credentials)
    return {"ok": True, "data": result}
```

---

#### [MODIFY] [security.py](file:///c:/Users/msina/OneDrive/Desktop/sv/app/backend/svapp-backend/app/core/security.py)

**No changes needed.** The new endpoints validate the Azure token directly inside `service.py` using `create_fresh_supabase_client().auth.get_user(token)`, which is the same pattern already used throughout the codebase. The provider check is done in the service layer where we have access to the user metadata.

The existing `get_current_user_no_device_check` dependency is still used by `POST /auth/register` — no change needed there.

---

#### [MODIFY] [ratelimit.py](file:///c:/Users/msina/OneDrive/Desktop/sv/app/backend/svapp-backend/app/core/ratelimit.py)

**One-line change** to include the new verification routes in strict auth rate limiting (5 req/min/IP):

```python
# Line 281 — update the is_auth_strict condition
is_auth_strict = (
    path.startswith("/auth/send-otp") or
    path.startswith("/auth/verify-otp") or
    path.startswith("/auth/login") or
    path.startswith("/auth/signup/verify-microsoft") or
    path.startswith("/auth/forgot-password/verify-microsoft")
)
```

---

### What Stays Untouched — Full List

| Component | Status |
|---|---|
| `public.users` table | ✅ Zero schema or data changes |
| Supabase Auth users | ✅ Not touched — OTP-created users keep working |
| `POST /auth/login` | ✅ Identical code |
| `POST /auth/register` | ✅ Identical code |
| `POST /auth/forgot-password/reset` | ✅ Identical code |
| `GET /auth/me` | ✅ Identical code |
| `PUT /auth/profile` | ✅ Identical code |
| `POST /auth/logout` | ✅ Identical code |
| `DELETE /auth/account` | ✅ Identical code |
| `POST /auth/send-otp` | ✅ Kept for rollback |
| `POST /auth/verify-otp` | ✅ Kept for rollback |
| `POST /auth/forgot-password/send-otp` | ✅ Kept for rollback |
| `POST /auth/forgot-password/verify-otp` | ✅ Kept for rollback |
| `email.py` (Postmark) | ✅ Not modified — stays for OTP rollback |
| `database.py` | ✅ Identical |
| `config.py` | ✅ Identical — no new env vars needed for backend |
| `redis.py` | ✅ Identical |
| All non-auth modules | ✅ Identical |

---

## Files Changed Summary

| File | Action | Risk |
|---|---|---|
| `migrations/versions/add_university_domains_table.sql` | NEW | None — creates new table |
| `scripts/seed_university_domains.py` | NEW | None — utility script |
| `scripts/university_domains_seed.json` | NEW | None — data file |
| `app/modules/auth/schemas.py` | ADD models | None — additive only |
| `app/modules/auth/service.py` | ADD 3 methods | None — existing methods untouched |
| `app/modules/auth/router.py` | ADD 3 routes | None — existing routes untouched |
| `app/core/ratelimit.py` | MODIFY 1 line | Minimal — only adds paths to rate limit |

**Total: 3 new files, 4 modified files. No deletions.**

---

## Verification Plan

### After Backend Deployment
1. **Existing login still works:** `POST /auth/login` with existing user credentials → ✅ success
2. **Existing profile fetch:** `GET /auth/me` with valid token → ✅ returns profile
3. **New institutions endpoint:** `GET /auth/institutions` → ✅ returns university list
4. **OTP endpoints still work:** `POST /auth/send-otp` → ✅ OTP sent (rollback path)
5. **Microsoft signup verification:** `POST /auth/signup/verify-microsoft` with Azure Bearer token → test with valid and invalid domains
6. **Microsoft recovery verification:** `POST /auth/forgot-password/verify-microsoft` → test with existing and non-existing accounts

### What Frontend Team Will Test
- Full sign-up flow: Microsoft → domain validation → password → profile → logged in
- Invalid university rejection screen
- Existing account redirect to login
- Forgot password: Microsoft verify → reset password → login
- All existing login flows unaffected

---

## Deployment Order

1. ✅ Create `university_domains` table in Supabase (run SQL migration)
2. ✅ Seed university domains (run seed script)  
3. ✅ Deploy backend with new endpoints (Railway redeploy)
4. ✅ Verify existing login still works
5. ✅ Test new endpoints via Postman
6. ✅ Hand off frontend implementation doc to frontend team
7. ✅ Frontend team ships updated mobile build
8. ✅ QA on development builds (iOS + Android)
