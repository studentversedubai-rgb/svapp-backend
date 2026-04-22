# StudentVerse Security Audit & Hardening Report

This document outlines the FAANG-level security protections implemented in the `svapp-backend` FastAPI backend, the sensitive environment variables required, and the remaining security tasks the team must complete before production.

## 1. Protections Implemented

### Global Rate Limiting
- **Auth Endpoints** (`/auth/send-otp`, `/auth/verify-otp`): Strictly limited to **5 requests per minute per IP**.
- **Payment Endpoints** (`/payments/*`): Strictly limited to **10 requests per minute per authenticated user**.
- **Authenticated Endpoints**: Default limited to **60 requests per minute per user** via token extraction.
- **Public Endpoints**: Default limited to **30 requests per minute per IP**.
- *Mechanism*: A custom `RateLimitMiddleware` leveraging a Redis sliding-window algorithm and returning `429 Too Many Requests` with a `Retry-After` header.

### Security Middlewares
- **Security HeadersMiddleware**: Automatically strips server info and attaches `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, `Strict-Transport-Security`, `Content-Security-Policy: default-src 'none'`, `Referrer-Policy`, and `Permissions-Policy`.
- **Request Size Limit Middleware**: Rejects any request payloads larger than **1MB** with a `413 Request Entity Too Large` error to prevent Denial of Service (DoS) memory floods.
- **Logging Middleware**: Logs structured request pathways and timings while explicitly masking payload bodies and authentication tokens.

### Data Protection & Information Disclosure Mitigations
- **Generic Error Masking**: Unhandled exceptions (500), Not Found (404), and Validation Errors (422) are intercepted globally in `main.py`. This hides database schemas, stack traces, and precise Pydantic internal structures from potential attackers.
- **Schema Hardening**: All critical Pydantic schemas across Auth, Payments, and Offers have been updated to include:
  - `model_config = ConfigDict(extra='forbid')` to reject JSON pollution.
  - Strict string boundaries (`max_length`).
  - E.164 Regex enforcement for phone numbers (`^\+?[1-9]\d{1,14}$`).
  - Pre-validators that reject raw HTML inputs `<, >, script, javascript:` in free-text fields.
  - Logical boundaries blocking past dates on ticket purchases.

### Authentication & CORS
- **JWT Integrity**: Tokens are validated rigorously against the Supabase internal keys. Validated User IDs are extracted dynamically and injected directly into dependencies, ignoring potentially spoofed `user_id`s in JSON requests.
- **Strict CORS**: `allow_origins=["*"]` has been eradicated. The application firmly binds origins to the injected `settings.allowed_origins_list` derived safely from the `.env` file. Pydantic strictly validates configurations on boot and raises loud exceptions before allowing the environment to run with dangerously omitted keys.

## 2. Security-Sensitive Environment Variables
The following environment variables contain powerful secrets or strict configuration controls and must be carefully guarded.
- `JWT_SECRET`: For cryptographic validation (or manual overrides).
- `SUPABASE_SERVICE_KEY`: Grants bypass-RLS root database access.
- `OPENROUTER_API_KEY`: Billed API key providing LLM inference.
- `RESEND_API_KEY`: Email routing key.
- `REDIS_PASSWORD`: Caching datastore authentication.
- `ALLOWED_ORIGINS`: Defines exactly which frontend clients can breach the CORS barrier. Ensure only active domains populate this list.

## 3. Remaining SECURITY TODOs (Action Required)

1. **Dependency Upgrades**:
   - `requirements.txt` contains rigidly pinned older dependencies (e.g. `fastapi==0.109.0`, `pydantic==2.5.3`). A secondary review referencing CVE vulnerability databases is necessary before upgrading these to avoid silently breaking codebase features.
2. **Webhook Cryptographic Signatures**:
   - The current `/payments/tickets/create-mock-order` endpoint simulates payments securely under JWT auth. However, when the real Stripe webhook replaces this, **Stripe Signature verification must be the absolute first middleware check** before any local database functions are allowed to execute.
