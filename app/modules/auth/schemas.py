"""
Authentication Schemas

Pydantic models for authentication requests.
"""

from pydantic import BaseModel, EmailStr, Field

class SendOTPRequest(BaseModel):
    """Request to send OTP"""
    email: EmailStr = Field(..., description="University email address")

class VerifyOTPRequest(BaseModel):
    """Request to verify OTP"""
    email: EmailStr = Field(..., description="University email address")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code")
