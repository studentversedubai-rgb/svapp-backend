"""
Authentication Router

Handles OTP-based authentication.
"""

from fastapi import APIRouter, HTTPException, status
from app.modules.auth.schemas import SendOTPRequest, VerifyOTPRequest
from app.modules.auth.service import auth_service

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
