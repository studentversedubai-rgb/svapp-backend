"""
Authentication Router

Handles OTP-based authentication.
"""

from fastapi import APIRouter, HTTPException, status, Depends
from app.modules.auth.schemas import (
    SendOTPRequest, 
    VerifyOTPRequest,
    RegisterRequest,
    LoginRequest,
    AuthResponse,
    ProfileResponse,
    UserProfile,
    UserStats,
    UserPreferences
)
from app.modules.auth.service import auth_service
from app.core.security import get_current_user
from typing import Dict

router = APIRouter()


@router.post("/send-otp")
async def send_otp(request: SendOTPRequest):
    """
    Send OTP to user's university email
    """
    return await auth_service.send_otp(request.email)


@router.post("/verify-otp")
async def verify_otp(request: VerifyOTPRequest):
    """
    Verify OTP and authenticate user
    """
    return await auth_service.verify_otp(request.email, request.code)


@router.post("/register", response_model=AuthResponse)
async def register(request: RegisterRequest):
    """
    Register a new user with Supabase Auth
    """
    return await auth_service.register(request.email, request.password, request.name)


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """
    Login user with Supabase Auth
    """
    return await auth_service.login(request.email, request.password)


@router.get("/me", response_model=ProfileResponse)
async def get_me(current_user: Dict = Depends(get_current_user)):
    """
    Get current user profile (protected route)
    """
    # Build profile response from user data
    user_profile = UserProfile(
        id=current_user.get("id"),
        email=current_user.get("email"),
        phone_number=current_user.get("phone_number"),
        student_id=current_user.get("student_id"),
        university=current_user.get("university"),
        avatar_url=current_user.get("avatar_url")
    )
    
    # Mock stats and preferences (will be real data in later phases)
    stats = UserStats()
    preferences = UserPreferences()
    
    return ProfileResponse(
        user=user_profile,
        stats=stats,
        preferences=preferences
    )


@router.post("/logout")
async def logout(current_user: Dict = Depends(get_current_user)):
    """
    Logout user (protected route)
    """
    # Note: JWT tokens are stateless, so logout is handled client-side
    # In future, could implement token blacklisting with Redis
    return {"message": "Logged out successfully"}


@router.post("/refresh")
async def refresh_token():
    """
    Refresh JWT access token using refresh token
    
    Steps:
    1. Validate refresh token with Supabase
    2. Issue new access token
    3. Optionally rotate refresh token
    
    Returns:
        New JWT access token
    """
    # TODO: Implement token refresh logic
    pass
