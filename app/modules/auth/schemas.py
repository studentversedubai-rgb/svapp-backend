"""
Authentication Schemas

Pydantic models for authentication requests and responses.
"""

from typing import Optional
from pydantic import BaseModel, EmailStr, Field

class SendOTPRequest(BaseModel):
    """Request to send OTP"""
    email: EmailStr = Field(..., description="University email address")

class VerifyOTPRequest(BaseModel):
    """Request to verify OTP"""
    email: EmailStr = Field(..., description="University email address")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code")

class RegisterRequest(BaseModel):
    """Request to register a new user"""
    email: EmailStr = Field(..., description="University email address")
    password: str = Field(..., min_length=8, description="User password")
    name: str = Field(..., min_length=1, description="User's full name")

class LoginRequest(BaseModel):
    """Request to login"""
    email: EmailStr = Field(..., description="Email address")
    password: str = Field(..., description="User password")

class UserData(BaseModel):
    """User data in response"""
    id: str = Field(..., description="User UUID")
    name: str = Field(..., description="User's full name")
    email: str = Field(..., description="User's email")

class AuthResponse(BaseModel):
    """Response after successful authentication"""
    token: str = Field(..., description="Access token")
    user: UserData = Field(..., description="User data")

class UserProfile(BaseModel):
    """User profile data for /me endpoint"""
    id: str
    email: str
    phoneNumber: Optional[str] = Field(None, alias="phone_number")
    studentId: Optional[str] = Field(None, alias="student_id")
    university: Optional[str] = None
    avatar: Optional[str] = Field(None, alias="avatar_url")
    
    class Config:
        populate_by_name = True  # Allow both camelCase and snake_case

class UserStats(BaseModel):
    """User statistics (mocked for now)"""
    totalSaved: str = "£0"
    activeDeals: int = 0
    visits: int = 0

class UserPreferences(BaseModel):
    """User preferences (mocked for now)"""
    notificationsEnabled: bool = True
    darkModeEnabled: bool = True

class ProfileResponse(BaseModel):
    """Response for GET /me endpoint"""
    user: UserProfile
    stats: UserStats
    preferences: UserPreferences
