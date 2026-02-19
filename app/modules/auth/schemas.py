"""
Authentication Schemas

Pydantic models for authentication requests and responses.
"""

from typing import Optional, Any, Dict
from pydantic import BaseModel, EmailStr, Field

class SendOTPRequest(BaseModel):
    """Request to send OTP"""
    email: EmailStr = Field(..., description="University email address")

class VerifyOTPRequest(BaseModel):
    """Request to verify OTP"""
    email: EmailStr = Field(..., description="University email address")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code")

class RegisterRequest(BaseModel):
    """Request to complete user registration/profile"""
    email: EmailStr = Field(..., description="University email address")
    first_name: str = Field(..., min_length=1, description="First name")
    last_name: str = Field(..., min_length=1, description="Last name")
    nationality: Optional[str] = Field(None, description="Nationality")
    university: Optional[str] = Field(None, description="University name")
    phone_number: Optional[str] = Field(None, description="Phone number")
    age: Optional[int] = Field(None, description="User age")
    profile_picture_url: Optional[str] = Field(None, alias="avatar_url", description="Profile picture URL")
    device_id: Optional[str] = Field(None, description="Device ID for single device login")

    class Config:
        populate_by_name = True

class ProfileUpdateRequest(BaseModel):
    """Request to update allowed profile fields"""
    university: Optional[str] = Field(None, description="University name")
    nationality: Optional[str] = Field(None, description="Nationality")
    phone_number: Optional[str] = Field(None, description="Phone number")
    profile_picture_url: Optional[str] = Field(None, alias="avatar_url", description="Profile picture URL")

    class Config:
        populate_by_name = True

class LoginRequest(BaseModel):
    """Request to login"""
    email: EmailStr = Field(..., description="Email address")
    password: str = Field(..., description="User password")

class UserData(BaseModel):
    """User data in response"""
    id: str = Field(..., description="User UUID")
    email: str = Field(..., description="User's email")
    first_name: Optional[str] = Field(None, description="First name")
    last_name: Optional[str] = Field(None, description="Last name")

class AuthResponse(BaseModel):
    """Response after successful authentication"""
    ok: bool = True
    data: Dict[str, Any] = Field(..., description="Auth data including token and user")

class UserProfile(BaseModel):
    """User profile data for /me endpoint"""
    id: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    nationality: Optional[str] = None
    university: Optional[str] = None
    phone_number: Optional[str] = None
    age: Optional[int] = None
    avatar_url: Optional[str] = None
    account_type: Optional[str] = "free"
    
    # Computed/Legacy fields
    full_name: Optional[str] = None 

    class Config:
        populate_by_name = True  # Allow both camelCase and snake_case

class UserStats(BaseModel):
    """User statistics"""
    total_saved: float = 0.0
    total_spent: float = 0.0
    total_redemptions: int = 0
    subscription_status: str = "free"

class UserPreferences(BaseModel):
    """User preferences (mocked for now)"""
    notifications_enabled: bool = True
    dark_mode_enabled: bool = True

class ProfileResponse(BaseModel):
    """Response for GET /me and GET /profile/analytics endpoint"""
    ok: bool = True
    data: Any

class AnalyticsResponse(BaseModel):
    """Response for analytics"""
    ok: bool = True
    data: UserStats
