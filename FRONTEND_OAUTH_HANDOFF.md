# Frontend Implementation Guide — Microsoft OAuth Authentication

## For: Frontend Team
## Status: Ready for implementation (backend is deployed)

---

## Overview

We are replacing the OTP-based sign-up and forgot-password flows with Microsoft Azure OAuth via Supabase. **The login flow (email + password) stays exactly the same.**

### What's new on the backend

| Endpoint | Purpose |
|---|---|
| `GET /auth/institutions` | Returns verified university list (replaces hardcoded `constants/universities.ts`) |
| `POST /auth/signup/verify-microsoft` | Validates Azure OAuth session for sign-up, creates account |
| `POST /auth/forgot-password/verify-microsoft` | Validates Azure OAuth session for password recovery |

All existing endpoints remain unchanged.

---

## Prerequisites

### Environment Variables

Add these to your `.env`:
```
EXPO_PUBLIC_SUPABASE_URL=<your-supabase-project-url>
EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<your-supabase-anon-key>
```

Get these from the Supabase Dashboard → Settings → API.

### Supabase Dashboard Configuration

Ensure the following is done (by the backend/infra team):
1. **Azure provider** is enabled in Authentication → Providers → Azure
2. **Redirect URL** `student-verse://auth/oauth-callback` is added in Authentication → URL Configuration

### Build Requirement

> ⚠️ **OAuth does NOT work in Expo Go.** You must test with:
> - `npx expo run:ios` (development build)
> - `npx expo run:android` (development build)

---

## New Files to Create

### 1. `services/supabase.ts` — Supabase Client

Create a dedicated Supabase client used ONLY for OAuth initiation and callback handling. This is NOT the app's primary auth mechanism — the backend token remains the authority.

```typescript
import { createClient } from '@supabase/supabase-js';
import * as SecureStore from 'expo-secure-store';
import 'react-native-url-polyfill/auto';

const supabaseUrl = process.env.EXPO_PUBLIC_SUPABASE_URL!;
const supabaseAnonKey = process.env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY!;

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    storage: {
      getItem: async (key: string) => {
        return await SecureStore.getItemAsync(key);
      },
      setItem: async (key: string, value: string) => {
        await SecureStore.setItemAsync(key, value);
      },
      removeItem: async (key: string) => {
        await SecureStore.deleteItemAsync(key);
      },
    },
    autoRefreshToken: false,
    persistSession: false,
    detectSessionInUrl: false,
  },
});
```

**Dependencies to install:**
```bash
npx expo install @supabase/supabase-js react-native-url-polyfill
```

### 2. `app/auth/oauth-callback.tsx` — OAuth Callback Handler

This screen handles the deep link return from Microsoft sign-in.

**Responsibilities:**
1. Parse the deep link URL for the OAuth code/tokens
2. Exchange with Supabase to get a session
3. Read the stored `oauth_flow` flag to determine if this was a sign-up or forgot-password flow
4. Call the appropriate backend endpoint with the Supabase Azure session token
5. Route to the next screen based on the result

**Flow logic:**

```
On mount:
  1. Get the URL that opened this screen (from Expo Linking)
  2. Call supabase.auth.exchangeCodeForSession() or supabase.auth.setSession()
  3. Get the session: const { data: { session } } = await supabase.auth.getSession()
  4. If no session → show error, redirect back
  5. Read oauth_flow from AsyncStorage
  
  If oauth_flow === 'signup':
    6. Call authService.verifyMicrosoftSignup(session.access_token)
    7. On success → store the returned access_token, navigate to signup step 2 (password)
       Pass the verified email and university_name as params
    8. On 400 (unsupported domain) → navigate to invalid-university screen
    9. On 409 (account exists) → show alert, navigate to login
    
  If oauth_flow === 'forgot-password':
    6. Call authService.verifyMicrosoftForgotPassword(session.access_token)
    7. On success → navigate to reset-password screen with { email, resetToken }
    8. On 404 (no account) → show error
  
  Finally:
    - Clear the Supabase session (it's transient, not the app's auth session)
    - Clear oauth_flow from AsyncStorage
```

### 3. `app/auth/invalid-university.tsx` — Rejection Screen

New screen shown when the user's Microsoft email domain is not in the verified whitelist.

**Requirements:**
- Match existing StudentVerse auth theme (gradient background, same typography)
- Title: "University Not Supported"
- Body: "Your university is not yet available on StudentVerse. We're continuously adding new universities."
- Button: "Try Again" → navigates back to signup
- Do NOT expose technical details (no domain names, no error codes)

---

## Files to Modify

### 4. `services/auth.ts` — Add New API Methods

Add these methods to the `authService` object (keep all existing methods):

```typescript
// New methods for Microsoft OAuth
getInstitutions: async (): Promise<{university_name: string, domain: string}[]> => {
  const response = await apiClient.get('/auth/institutions');
  return response.data.data || response.data;
},

verifyMicrosoftSignup: async (azureToken: string): Promise<any> => {
  // Use the Azure OAuth token, not the app's stored token
  const response = await apiClient.post('/auth/signup/verify-microsoft', {}, {
    headers: { Authorization: `Bearer ${azureToken}` }
  });
  return response.data.data || response.data;
},

verifyMicrosoftForgotPassword: async (azureToken: string): Promise<any> => {
  const response = await apiClient.post('/auth/forgot-password/verify-microsoft', {}, {
    headers: { Authorization: `Bearer ${azureToken}` }
  });
  return response.data.data || response.data;
},
```

> ⚠️ **Important:** The `verifyMicrosoftSignup` and `verifyMicrosoftForgotPassword` methods must pass the **Azure OAuth session token** as the Bearer token — NOT the app's stored auth token. These endpoints validate the Azure session, not the app session.

### 5. `services/api.ts` — Update 401 Handler

Add the new auth-flow endpoints to the `isAuthRequest` check so the 401 interceptor doesn't accidentally trigger a "session expired" redirect during OAuth verification:

```typescript
const isAuthRequest = requestUrl.includes('/auth/login') || 
                      requestUrl.includes('/auth/logout') ||
                      requestUrl.includes('/auth/send-otp') ||
                      requestUrl.includes('/auth/verify-otp') ||
                      requestUrl.includes('/auth/register') ||
                      requestUrl.includes('/auth/signup/verify-microsoft') ||
                      requestUrl.includes('/auth/forgot-password/verify-microsoft');
```

### 6. `app/auth/signup.tsx` — Refactor Sign-Up Wizard

The wizard changes from 8 steps to 7 steps:

| Current | New |
|---|---|
| Step 1: Enter university email | Step 1: **"Continue with Microsoft"** button |
| Step 2: Verify 6-digit OTP | *(removed)* |
| Step 3: Create password | Step 2: Create password (email shown read-only) |
| Step 4: First/Last name | Step 3: First/Last name |
| Step 5: Nationality | Step 4: Nationality |
| Step 6: Date of birth | Step 5: Date of birth |
| Step 7: University name | Step 6: University name (fetched from backend) |
| Step 8: Phone number → submit | Step 7: Phone number → submit |

**Step 1 changes:**
- Remove the email TextInput
- Remove the `blockedDomains` array and `validateStudentEmail()` function
- Add a **"Continue with Microsoft"** button styled with the SV gradient
- On tap:
  1. Store `oauth_flow = 'signup'` in AsyncStorage
  2. Call `supabase.auth.signInWithOAuth({ provider: 'azure', options: { redirectTo: 'student-verse://auth/oauth-callback' } })`
  3. This opens the Microsoft sign-in in a web browser
  4. After sign-in, the user is redirected to the oauth-callback route

**After OAuth callback returns successfully:**
- The verified email comes back as a route param or stored in context
- Set `formData.universityEmail` to the verified email (read-only)
- Advance to step 2 (password creation)
- The email field in subsequent steps should be locked/read-only

**Step 7 (University Name):**
- Replace the hardcoded `universities` import from `constants/universities.ts`
- Instead, fetch from `authService.getInstitutions()` on mount
- Show the same `SearchableDropdown` but with data from the backend
- Remove the "Other / Not listed" option (strict whitelist means only verified universities appear)
- If you want to keep a manual entry fallback, that's a product decision — the backend will accept any university name in the `register` call since the domain was already validated

**Step 8 → Step 7 (Final step):**
- `completeRegistration()` call stays the same
- Update analytics tag from `method: 'otp'` to `method: 'azure_oauth'`

**OTP-related code to remove from active flow:**
- `otp` state variable
- `otpError` state variable
- `resendCooldown` timer
- `sendOtp()` / `verifyOtp()` calls
- OTP step rendering (case 2 in the current render switch)
- Resend OTP button

### 7. `app/auth/forgot-password.tsx` — Replace OTP with Microsoft

**Current flow:** Enter email → send OTP → navigate to forgot-otp.tsx
**New flow:** "Verify with Microsoft" button → navigate to reset-password.tsx

Replace the email input and "Continue" button with:
1. A "Verify with Microsoft" button
2. On tap:
   - Store `oauth_flow = 'forgot-password'` in AsyncStorage
   - Launch `supabase.auth.signInWithOAuth({ provider: 'azure', options: { redirectTo: 'student-verse://auth/oauth-callback' } })`
3. The oauth-callback handler will call the backend and navigate to reset-password.tsx

### 8. `app/auth/forgot-otp.tsx` — Deprecate

This screen is no longer used in the active flow. You can either:
- Remove it entirely
- Or keep the file and just remove it from the navigation stack

**Recommendation:** Keep the file for now (rollback safety) but ensure no active navigation points to it.

### 9. `app/auth/_layout.tsx` — Add New Screens

Add the new screens to the auth Stack:

```tsx
<Stack.Screen name="oauth-callback" />
<Stack.Screen name="invalid-university" />
```

### 10. `contexts/AuthContext.tsx` — Minor Updates

- The `sendOTP` and `verifyOTP` methods can remain in the context (for rollback) but they won't be called from the active signup flow anymore
- Update `completeRegistration` analytics from `method: 'otp'` to `method: 'azure_oauth'`
- Keep all other methods (`login`, `logout`, `deleteAccount`, `updateUser`) untouched

### 11. `app.json` — No Changes Needed

The scheme `student-verse` is already configured. No changes required.

---

## API Response Formats

### `GET /auth/institutions`
```json
{
  "ok": true,
  "data": [
    {"university_name": "American University of Sharjah (AUS)", "domain": "aus.edu"},
    {"university_name": "Zayed University (ZU)", "domain": "zu.ac.ae"}
  ]
}
```

### `POST /auth/signup/verify-microsoft`
**Request:** No body. Bearer token in Authorization header.

**Success (200):**
```json
{
  "ok": true,
  "data": {
    "status": "success",
    "message": "Microsoft verification successful. Please complete your registration.",
    "email": "student@aus.edu",
    "university_name": "American University of Sharjah (AUS)",
    "is_new_user": true,
    "access_token": "eyJ...",
    "token_type": "bearer",
    "user": {"id": "uuid", "email": "student@aus.edu"}
  }
}
```

**Error (400 - unsupported domain):**
```json
{
  "ok": false,
  "error": "Your university is not supported yet. Only verified UAE university email domains are accepted."
}
```

**Error (409 - account exists):**
```json
{
  "ok": false,
  "error": "An account with this email already exists. Please use the login screen."
}
```

### `POST /auth/forgot-password/verify-microsoft`
**Request:** No body. Bearer token in Authorization header.

**Success (200):**
```json
{
  "ok": true,
  "data": {
    "email": "student@aus.edu",
    "reset_token": "uuid-token"
  }
}
```

**Error (404 - no account):**
```json
{
  "ok": false,
  "error": "No account found with this email."
}
```

---

## Flow Diagrams

### Sign-Up Flow (New)
```
User taps "Sign Up"
  → Step 1: "Continue with Microsoft" button
  → Microsoft sign-in opens in browser
  → User signs in with university Microsoft account
  → Redirect back to app (oauth-callback)
  → oauth-callback calls POST /auth/signup/verify-microsoft
  → Backend validates: Azure provider ✓, domain whitelisted ✓, no existing account ✓
  → Backend creates Supabase Auth user + public.users row
  → Returns access_token + verified email
  → App stores token, advances to Step 2 (Create Password)
  → Steps 2-7: Password, Name, Nationality, DOB, University, Phone
  → Step 7: POST /auth/register (same as before)
  → User is logged in
```

### Login Flow (UNCHANGED)
```
User taps "Log In"
  → Enter email + password
  → POST /auth/login
  → Same as before — zero changes
```

### Forgot Password Flow (New)
```
User taps "Forgot Password"
  → "Verify with Microsoft" button
  → Microsoft sign-in opens in browser
  → Redirect back to app (oauth-callback)
  → oauth-callback calls POST /auth/forgot-password/verify-microsoft
  → Backend validates: Azure provider ✓, domain whitelisted ✓, account exists ✓
  → Returns reset_token
  → App navigates to reset-password screen
  → User sets new password
  → POST /auth/forgot-password/reset (same endpoint as before, with reset_token)
  → User returns to login
```

---

## Loading & Error States to Handle

| State | When | UI Treatment |
|---|---|---|
| Launching Microsoft | After tapping "Continue with Microsoft" | Show loading spinner or "Opening Microsoft..." |
| Returning from callback | OAuth callback screen loads | Show spinner with "Verifying..." |
| Verifying institution | Backend call in progress | Spinner continues |
| Invalid university | Backend returns 400 | Navigate to invalid-university screen |
| Account exists | Backend returns 409 | Show alert, navigate to login |
| OAuth cancelled | User closes Microsoft sign-in without completing | Return to previous screen, no error |
| Token expired | Backend returns 401 | Show error "Session expired, please try again" |
| Network error | No connectivity | Standard network error handling |

---

## Testing Checklist

- [ ] New sign-up: Microsoft → valid university → password → profile → logged in
- [ ] Sign-up with non-university Microsoft account → invalid-university screen
- [ ] Sign-up with already-registered email → 409 → redirect to login
- [ ] OAuth cancel (close Microsoft browser) → return to signup, no crash
- [ ] Forgot password: Microsoft → valid account → reset password → login works
- [ ] Forgot password: Microsoft → no account → 404 error shown
- [ ] Existing login (email + password) → still works unchanged
- [ ] `GET /auth/institutions` → dropdown shows backend list
- [ ] Loading states don't flash or hang
- [ ] All screens match SV auth theme (gradients, typography, spacing)
- [ ] Works on iOS development build
- [ ] Works on Android development build
