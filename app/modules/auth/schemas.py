"""
Authentication Schemas

Pydantic models for authentication requests and responses.

NO BUSINESS LOGIC - Structure only
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class SendOTPRequest(BaseModel):
    """Request to send OTP"""
    email: EmailStr = Field(..., description="University email address")


class SendOTPResponse(BaseModel):
    """Response after sending OTP"""
    success: bool = True
    message: str = "If this email is registered, an OTP has been sent"
    # Never reveal if email exists for security


class VerifyOTPRequest(BaseModel):
    """Request to verify OTP"""
    email: EmailStr = Field(..., description="University email address")
    otp: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code")


class AuthTokens(BaseModel):
    """JWT tokens"""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Token expiry in seconds")


class AuthResponse(BaseModel):
    """Response after successful authentication"""
    success: bool = True
    message: str
    user_id: str = Field(..., description="User UUID from Supabase")
    email: str
    tokens: AuthTokens
    is_new_user: bool = Field(..., description="True if this is first login")


class RefreshTokenRequest(BaseModel):
    """Request to refresh access token"""
    refresh_token: str = Field(..., description="JWT refresh token")


class RefreshTokenResponse(BaseModel):
    """Response with new access token"""
    success: bool = True
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class LogoutResponse(BaseModel):
    """Response after logout"""
    success: bool = True
    message: str = "Logged out successfully"
