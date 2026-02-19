"""
Authentication Router

Handles OTP-based authentication and Profile Management.
"""

from fastapi import APIRouter, HTTPException, status, Depends
from app.modules.auth.schemas import (
    SendOTPRequest, 
    VerifyOTPRequest,
    RegisterRequest,
    ProfileUpdateRequest,
    LoginRequest,
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
async def verify_otp(request: VerifyOTPRequest):
    """
    Verify OTP and authenticate user.
    Returns Access Token.
    """
    result = await auth_service.verify_otp(request.email, request.code)
    return AuthResponse(data=result)


@router.post("/register", response_model=ProfileResponse)
async def register(
    request: RegisterRequest, 
    current_user: Dict = Depends(get_current_user_no_device_check)
):
    """
    Complete user registration / Update profile.
    
    Requires Authentication (JWT) obtained from verify-otp.
    Updates the authenticated user's profile with required details.
    """
    updated_user = await auth_service.complete_registration(current_user["id"], request)
    
    # Map to UserProfile
    profile = UserProfile(**updated_user)
    profile.full_name = f"{profile.first_name} {profile.last_name}"
    
    return ProfileResponse(data=profile)


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """
    Legacy Login (Email/Password) - Not primary flow.
    """
    result = await auth_service.login(request.email, request.password)
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
async def logout(current_user: Dict = Depends(get_current_user)):
    """
    Logout user (stateless, client should discard token).
    """
    return {"message": "Logged out successfully"}
