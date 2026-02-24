"""
Authentication Schemas

Pydantic models for authentication requests and responses.
"""

import re
from typing import Optional, Any, Dict
from pydantic import BaseModel, EmailStr, Field, field_validator, HttpUrl

class SendOTPRequest(BaseModel):
    """Request to send OTP"""
    email: EmailStr = Field(..., description="University email address")

class VerifyOTPRequest(BaseModel):
    """Request to verify OTP"""
    email: EmailStr = Field(..., description="University email address")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code")

    @field_validator("code")
    @classmethod
    def code_must_be_digits(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("OTP code must contain only digits")
        return v

class RegisterRequest(BaseModel):
    """Request to complete user registration/profile"""
    email: EmailStr = Field(..., description="University email address")
    name: str = Field(..., min_length=2, max_length=100, description="Full name")
    first_name: str = Field(..., min_length=2, max_length=50, description="First name")
    last_name: str = Field(..., min_length=2, max_length=50, description="Last name")
    student_id: Optional[str] = Field(None, min_length=3, max_length=30, description="Student ID")
    nationality: Optional[str] = Field(None, min_length=2, max_length=60, description="Nationality")
    university: Optional[str] = Field(None, min_length=2, max_length=100, description="University name")
    phone_number: Optional[str] = Field(None, description="Phone number in international format (e.g. +971501234567)")
    age: Optional[int] = Field(None, ge=13, le=120, description="User age (13-120)")
    profile_picture_url: Optional[str] = Field(None, alias="avatar_url", description="Profile picture URL")
    device_id: Optional[str] = Field(None, min_length=5, max_length=255, description="Device ID for single device login")

    @field_validator("name", "first_name", "last_name")
    @classmethod
    def name_must_be_valid(cls, v: str, info) -> str:
        v = v.strip()
        if not v:
            raise ValueError(f"{info.field_name} cannot be empty or whitespace only")
        if not re.match(r"^[a-zA-Z\s\-'.]+$", v):
            raise ValueError(f"{info.field_name} must contain only letters, spaces, hyphens, or apostrophes")
        return v

    @field_validator("nationality")
    @classmethod
    def nationality_must_be_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not re.match(r"^[a-zA-Z\s\-]+$", v):
            raise ValueError("Nationality must contain only letters, spaces, or hyphens")
        return v

    @field_validator("university")
    @classmethod
    def university_must_be_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not re.match(r"^[a-zA-Z0-9\s\-&',.()]+$", v):
            raise ValueError("University name contains invalid characters")
        return v

    @field_validator("student_id")
    @classmethod
    def student_id_must_be_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not re.match(r"^[a-zA-Z0-9\-_]+$", v):
            raise ValueError("Student ID must contain only letters, numbers, hyphens, or underscores")
        return v

    @field_validator("phone_number")
    @classmethod
    def phone_must_be_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not re.match(r"^\+[1-9]\d{6,14}$", v):
            raise ValueError("Phone number must be in international format (e.g. +971501234567)")
        return v

    @field_validator("profile_picture_url")
    @classmethod
    def url_must_be_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not re.match(r"^https?://", v):
            raise ValueError("Profile picture URL must start with http:// or https://")
        return v

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
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    student_id: Optional[str] = None
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
