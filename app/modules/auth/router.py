"""
Authentication Router

Handles OTP-based authentication and registration.
IMPORTANT: Uses Supabase Auth - no password storage in this backend.

Endpoints:
- POST /auth/send-otp: Send OTP to university email
- POST /auth/verify-otp: Verify OTP and register/login user
- POST /auth/refresh: Refresh JWT token

NO BUSINESS LOGIC - Structure only
"""

from fastapi import APIRouter, Depends, HTTPException, status
# from app.modules.auth.schemas import (
#     SendOTPRequest,
#     VerifyOTPRequest,
#     AuthResponse,
#     RefreshTokenRequest
# )
# from app.modules.auth.service import AuthService
# from app.core.security import get_current_user

router = APIRouter()


@router.post("/send-otp")
async def send_otp():
    """
    Send OTP to user's university email
    
    Steps:
    1. Validate email is university domain
    2. Check rate limiting
    3. Generate OTP via Supabase Auth
    4. Send OTP email
    5. Store OTP in Redis with expiry
    
    Returns:
        Success message (never reveal if email exists)
    """
    # TODO: Implement OTP sending logic
    pass


@router.post("/verify-otp")
async def verify_otp():
    """
    Verify OTP and authenticate user
    
    Steps:
    1. Verify OTP with Supabase Auth
    2. If valid and new user: create user record
    3. If valid and existing user: update last_login
    4. Return JWT tokens
    
    Returns:
        JWT access token and refresh token
    """
    # TODO: Implement OTP verification logic
    pass


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


@router.post("/logout")
async def logout():
    """
    Logout user (invalidate tokens)
    
    Steps:
    1. Get current user from JWT
    2. Invalidate refresh token in Supabase
    3. Optionally blacklist access token in Redis
    
    Returns:
        Success message
    """
    # TODO: Implement logout logic
    pass
