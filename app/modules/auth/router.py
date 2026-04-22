"""
Authentication Router

Handles OTP-based authentication and Profile Management.
"""

from fastapi import APIRouter, HTTPException, status, Depends, Request, Form, File, UploadFile
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.modules.auth.schemas import (
    SendOTPRequest, 
    VerifyOTPRequest,
    RegisterRequest,
    ProfileUpdateRequest,
    LoginRequest,
    ResetPasswordRequest,
    AuthResponse,
    ProfileResponse,
    AnalyticsResponse,
    UserProfile,
    UserStats,
)
from app.modules.auth.service import auth_service
from app.core.security import get_current_user, get_current_user_no_device_check
from app.modules.auth.dependencies import rate_limit_check
from typing import Dict, Any

router = APIRouter()


@router.post("/send-otp")
async def send_otp(request: SendOTPRequest):
    """
    Send OTP to user's university email
    """
    result = await auth_service.send_otp(request.email)
    # The default response format handler should ideally wrap this if we standardize ALL responses,
    # but here we manually wrap to ensure consistency with AuthResponse style if needed,
    # or rely on the dict being returned as JSON.
    # User requirement: "Return consistent JSON responses with 'ok', 'error', 'data' structure"
    # We should return {"ok": true, "data": result}
    return {"ok": True, "data": result}


@router.post("/verify-otp", response_model=AuthResponse)
async def verify_otp(request_body: VerifyOTPRequest, request: Request):
    """
    Verify OTP and authenticate user.
    Returns Access Token.
    """
    device_id = request.headers.get("X-Device-ID", "")
    result = await auth_service.verify_otp(request_body.email, request_body.code, device_id)
    return AuthResponse(data=result)


@router.post("/forgot-password/send-otp")
async def forgot_password_send_otp(request: SendOTPRequest):
    """
    Send OTP for forgot password flow
    """
    result = await auth_service.forgot_password_send_otp(request.email)
    return {"ok": True, "data": result}


@router.post("/forgot-password/verify-otp")
async def forgot_password_verify_otp(request: VerifyOTPRequest):
    """
    Verify OTP for forgot password flow and get a temporary reset token
    """
    result = await auth_service.forgot_password_verify_otp(request.email, request.code)
    return {"ok": True, "data": result}


@router.post("/forgot-password/reset")
async def forgot_password_reset(request: ResetPasswordRequest):
    """
    Reset password using the temporary reset token
    """
    result = await auth_service.forgot_password_reset(request.email, request.reset_token, request.new_password)
    return {"ok": True, "data": result}


@router.post("/manual-signup")
async def manual_signup(
    email: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    nationality: str = Form(""),
    university: str = Form(""),
    phone_number: str = Form(""),
    date_of_birth: str = Form(...),
    password: str = Form(...),
    student_id: str = Form(""),
    enrollment_document: UploadFile = File(...),
    student_id_document: UploadFile = File(...),
):
    """
    Create a pending-review account with uploaded verification documents.

    Public endpoint. Does not return an authenticated app session.
    """
    result = await auth_service.manual_signup(
        email=email,
        first_name=first_name,
        last_name=last_name,
        nationality=nationality or None,
        university=university or None,
        phone_number=phone_number or None,
        date_of_birth=date_of_birth,
        password=password,
        student_id=student_id or None,
        enrollment_document=enrollment_document,
        student_id_document=student_id_document,
    )
    return {"ok": True, "data": result}


@router.post("/manual-signup/resubmit")
async def manual_signup_resubmit(
    email: str = Form(...),
    password: str = Form(...),
    enrollment_document: UploadFile = File(...),
    student_id_document: UploadFile = File(...),
):
    """
    Re-submit verification documents for a previously rejected account.
    """
    result = await auth_service.manual_signup_resubmit(
        email=email,
        password=password,
        enrollment_document=enrollment_document,
        student_id_document=student_id_document,
    )
    return {"ok": True, "data": result}


@router.post("/register")
async def register(
    request: RegisterRequest,
    current_user: Dict = Depends(get_current_user_no_device_check),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())
):
    """
    Complete user registration / Update profile.

    Requires Authentication (JWT) obtained from verify-otp.
    Returns the updated profile AND a fresh access_token (the old one is
    invalidated by Supabase when the password is set).
    """
    result = await auth_service.complete_registration(
        current_user["id"], request, access_token=credentials.credentials
    )

    # Extract token fields before building UserProfile (UserProfile doesn't have them)
    new_token = result.pop("access_token", None)
    result.pop("token_type", None)

    profile = UserProfile(**result)
    if profile.first_name and profile.last_name:
        profile.full_name = f"{profile.first_name} {profile.last_name}"

    response_data: Dict[str, Any] = profile.model_dump()
    if new_token:
        response_data["access_token"] = new_token
        response_data["token_type"] = "bearer"

    return {"ok": True, "data": response_data}


@router.post("/login", response_model=AuthResponse)
async def login(request_body: LoginRequest, request: Request):
    """
    Legacy Login (Email/Password) - Not primary flow.
    """
    device_id = request.headers.get("X-Device-ID", "")
    result = await auth_service.login(request_body.email, request_body.password, device_id)
    return AuthResponse(data=result)


@router.get("/me", response_model=ProfileResponse)
async def get_me(current_user: Dict = Depends(get_current_user)):
    """
    Get current user profile (protected route).
    """
    # Map current_user dict to UserProfile model
    profile = UserProfile(**current_user)
    # logic for full name
    if profile.first_name and profile.last_name:
         profile.full_name = f"{profile.first_name} {profile.last_name}"
    
    return ProfileResponse(data=profile)


@router.put("/profile", response_model=ProfileResponse)
async def update_profile(
    request: ProfileUpdateRequest,
    current_user: Dict = Depends(get_current_user)
):
    """
    Update user profile fields.
    Allowed: phone_number, nationality, university, avatar_url.
    Not Allowed: email, first_name, last_name, device_id.
    """
    updated_user = await auth_service.update_profile(current_user["id"], request)

    profile = UserProfile(**updated_user)
    if profile.first_name and profile.last_name:
         profile.full_name = f"{profile.first_name} {profile.last_name}"

    return ProfileResponse(data=profile)


@router.post("/profile/image", response_model=ProfileResponse)
async def upload_profile_image(
    file: UploadFile = File(...),
    current_user: Dict = Depends(get_current_user),
):
    """
    Upload a profile picture.

    Stores the image in the public user-profile-images Supabase Storage bucket
    and updates users.avatar_url with the resolved public URL. Returns the full
    updated profile so the client does not need a follow-up /auth/me call.
    """
    await auth_service.upload_profile_image(current_user["id"], file)
    updated = await auth_service.get_profile(current_user["id"])

    profile = UserProfile(**updated)
    if profile.first_name and profile.last_name:
        profile.full_name = f"{profile.first_name} {profile.last_name}"

    return ProfileResponse(data=profile)


@router.get("/profile/analytics", response_model=AnalyticsResponse)
async def get_analytics(current_user: Dict = Depends(get_current_user)):
    """
    Get user savings and redemption analytics.
    """
    stats = await auth_service.get_user_analytics(current_user["id"])
    return AnalyticsResponse(data=stats)


@router.post("/logout")
async def logout(
    current_user: Dict = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())
):
    """
    Logout user — clears device binding and invalidates the Supabase JWT.
    """
    await auth_service.logout_user(current_user["id"], access_token=credentials.credentials)
    return {"message": "Logged out successfully"}


@router.delete("/account")
async def delete_account(
    current_user: Dict = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())
):
    """
    Permanently delete the authenticated user's account and all associated data.

    This is an irreversible operation required for App Store compliance.
    Deletes: user profile, redemptions, entitlements, ticket records,
    Stripe customer, Redis keys, and Supabase Auth user.
    """
    await auth_service.delete_account(current_user["id"], access_token=credentials.credentials)
    return {"ok": True, "data": {"message": "Account permanently deleted"}}


# ------------------------------------------------------------------
# Microsoft OAuth Verification Routes
# ------------------------------------------------------------------

@router.get("/institutions")
async def list_institutions():
    """
    Return list of supported universities for frontend dropdown.

    Public endpoint — no authentication required.
    Source of truth replaces hardcoded frontend university list.
    """
    result = await auth_service.list_verified_institutions()
    return {"ok": True, "data": result}


@router.post("/signup/verify-microsoft")
async def verify_microsoft_signup(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())
):
    """
    Verify Microsoft Azure OAuth session for new user sign-up.

    Expects: Bearer token from Supabase Azure OAuth session in Authorization header.
    No request body — the email is derived from the authenticated token, not client input.

    Returns: verified email, university name, and access token for registration completion.

    Error responses:
    - 400: unsupported university domain or invalid provider
    - 401: invalid or expired Azure session
    - 409: account with this email already exists
    """
    result = await auth_service.verify_microsoft_signup(credentials.credentials)
    return {"ok": True, "data": result}


@router.post("/forgot-password/verify-microsoft")
async def verify_microsoft_recovery(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())
):
    """
    Verify Microsoft Azure OAuth session for password recovery.

    Expects: Bearer token from Supabase Azure OAuth session in Authorization header.
    No request body — the email is derived from the authenticated token.

    Returns: email and a short-lived reset token (10 min TTL).
    The reset token is used with the existing POST /auth/forgot-password/reset endpoint.

    Error responses:
    - 400: unsupported university domain or invalid provider
    - 401: invalid or expired Azure session
    - 404: no account found with this email
    """
    result = await auth_service.verify_microsoft_recovery(credentials.credentials)
    return {"ok": True, "data": result}
