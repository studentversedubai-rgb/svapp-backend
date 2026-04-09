"""
Authentication Router

Handles OTP-based authentication and Profile Management.
"""

from fastapi import APIRouter, HTTPException, status, Depends, Request
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
    UserStats
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
