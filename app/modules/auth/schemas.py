"""
Authentication Schemas

Pydantic models for authentication requests and responses.
"""

import re
from typing import Optional, Any, Dict
from urllib.parse import urlparse
from pydantic import BaseModel, EmailStr, Field, field_validator, HttpUrl, ConfigDict

def validate_password_complexity(v: str) -> str:
    if not re.search(r'[A-Z]', v):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r'[a-z]', v):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r'[0-9]', v):
        raise ValueError("Password must contain at least one number")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
        raise ValueError("Password must contain at least one special character")
    return v


class SendOTPRequest(BaseModel):
    """Request to send OTP"""
    model_config = ConfigDict(extra='forbid')
    email: EmailStr = Field(..., description="University email address")

class VerifyOTPRequest(BaseModel):
    """Request to verify OTP"""
    model_config = ConfigDict(extra='forbid')
    email: EmailStr = Field(..., description="University email address")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code")

    @field_validator("code")
    @classmethod
    def code_must_be_digits(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("OTP code must contain only digits")
        return v

class RefreshTokenRequest(BaseModel):
    """Request to refresh an expired access token"""
    model_config = ConfigDict(extra='forbid')
    refresh_token: str = Field(..., description="Supabase refresh token")


class ResetPasswordRequest(BaseModel):
    """Request to reset password after OTP verification"""
    model_config = ConfigDict(extra='forbid')
    email: EmailStr = Field(..., description="University or personal email used to initiate reset")
    reset_token: str = Field(..., description="Reset token obtained from verifying forgot-password OTP")
    new_password: str = Field(..., min_length=8, max_length=100, description="New password")

    @field_validator("new_password")
    @classmethod
    def check_new_password(cls, v: str) -> str:
        return validate_password_complexity(v)



class SendPersonalEmailOTPRequest(BaseModel):
    """Request to send an OTP to a user's personal email."""
    model_config = ConfigDict(extra='forbid')
    personal_email: EmailStr = Field(..., description="Personal (non-university) email address")


class VerifyPersonalEmailOTPRequest(BaseModel):
    """Request to verify a personal-email OTP."""
    model_config = ConfigDict(extra='forbid')
    personal_email: EmailStr = Field(..., description="Personal email address")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code")

    @field_validator("code")
    @classmethod
    def code_must_be_digits(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("OTP code must contain only digits")
        return v


class SignupVerifyPersonalEmailOTPResponse(BaseModel):
    """Response after verifying a signup personal-email OTP."""
    ok: bool = True
    data: Dict[str, Any] = Field(..., description="Short-lived signup token keyed to the personal email")

class RegisterRequest(BaseModel):
    """Request to complete user registration/profile"""
    model_config = ConfigDict(extra='forbid', populate_by_name=True)
    email: EmailStr = Field(..., description="University email address")
    name: str = Field(..., min_length=2, max_length=100, description="Full name")
    first_name: str = Field(..., min_length=2, max_length=50, description="First name")
    last_name: str = Field(..., min_length=2, max_length=50, description="Last name")
    student_id: Optional[str] = Field(None, min_length=3, max_length=30, description="Student ID")
    nationality: Optional[str] = Field(None, min_length=2, max_length=60, description="Nationality")
    university: Optional[str] = Field(None, min_length=2, max_length=100, description="University name")
    phone_number: Optional[str] = Field(None, description="Phone number in international format (e.g. +971501234567)")
    age: Optional[int] = Field(None, ge=13, le=120, description="User age (13-120)")
    date_of_birth: Optional[str] = Field(None, description="Date of birth in YYYY-MM-DD format")
    profile_picture_url: Optional[str] = Field(None, alias="avatar_url", description="Profile picture URL")
    device_id: Optional[str] = Field(None, min_length=5, max_length=255, description="Device ID for single device login")
    password: Optional[str] = Field(None, min_length=8, description="User chosen password to set in Supabase Auth")

    @field_validator("password")
    @classmethod
    def check_password(cls, v) -> str:
        if v is None:
            return v
        return validate_password_complexity(v)
    
    @field_validator("name", "first_name", "last_name", "nationality", "university", "student_id", mode="before")
    @classmethod
    def strip_html_and_scripts(cls, v: Optional[str]) -> Optional[str]:
        if v and isinstance(v, str):
            if "<" in v or ">" in v or "script" in v.lower() or "javascript:" in v.lower():
                raise ValueError("Input contains invalid or dangerous characters")
        return v

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
        v = v.strip().replace(" ", "")  # Strip spaces
        if not re.match(r"^\+?[1-9]\d{1,14}$", v):
            raise ValueError("Phone number must be in international format (e.g. +971501234567)")
        return v

    @field_validator("profile_picture_url")
    @classmethod
    def url_must_be_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        try:
            parsed = urlparse(v)
            if parsed.scheme not in ("http", "https"):
                raise ValueError("Profile picture URL must use http or https")
            if not parsed.netloc:
                raise ValueError("Profile picture URL must have a valid domain")
        except ValueError:
            raise
        except Exception:
            raise ValueError("Profile picture URL is not valid")
        return v

class ProfileUpdateRequest(BaseModel):
    """Request to update allowed profile fields"""
    model_config = ConfigDict(extra='forbid', populate_by_name=True)

    first_name: Optional[str] = Field(None, min_length=1, max_length=60, description="First name")
    last_name: Optional[str] = Field(None, min_length=1, max_length=60, description="Last name")
    name: Optional[str] = Field(None, min_length=2, max_length=100, description="Full name (legacy)")
    student_id: Optional[str] = Field(None, min_length=3, max_length=30, description="Student ID")
    university: Optional[str] = Field(None, max_length=150, description="University name")
    nationality: Optional[str] = Field(None, max_length=60, description="Nationality")
    phone_number: Optional[str] = Field(None, max_length=20, description="Phone number")
    profile_picture_url: Optional[str] = Field(None, alias="avatar_url", description="Profile picture URL")

    @field_validator("first_name", "last_name", "name", "nationality", "university", "student_id", mode="before")
    @classmethod
    def strip_html_and_scripts(cls, v: Optional[str]) -> Optional[str]:
        if v and isinstance(v, str):
            if "<" in v or ">" in v or "script" in v.lower() or "javascript:" in v.lower():
                raise ValueError("Input contains invalid or dangerous characters")
        return v

class LoginRequest(BaseModel):
    """Request to login"""
    model_config = ConfigDict(extra='forbid')
    email: EmailStr = Field(..., description="Email address")
    password: str = Field(..., min_length=8, max_length=100, description="User password")

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
    personal_email: Optional[str] = None
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    student_id: Optional[str] = None
    nationality: Optional[str] = None
    university: Optional[str] = None
    phone_number: Optional[str] = None
    age: Optional[int] = None
    date_of_birth: Optional[str] = None  # YYYY-MM-DD from DB
    avatar_url: Optional[str] = None
    account_type: Optional[str] = "free"
    created_at: Optional[str] = None  # ISO timestamp — used as "Member Since" in app

    # Computed/Legacy fields
    full_name: Optional[str] = None

    class Config:
        populate_by_name = True

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


# ------------------------------------------------------------------
# Microsoft OAuth Verification Schemas
# ------------------------------------------------------------------

class InstitutionItem(BaseModel):
    """Single university entry for the institutions list."""
    university_name: str = Field(..., description="Official university name")
    domain: str = Field(..., description="Accepted email domain")

class InstitutionsListResponse(BaseModel):
    """Response for GET /auth/institutions"""
    ok: bool = True
    data: list = Field(default_factory=list, description="List of supported institutions")

class MicrosoftSignupVerifyResponse(BaseModel):
    """Response for POST /auth/signup/verify-microsoft"""
    ok: bool = True
    data: Dict[str, Any] = Field(..., description="Verified email, university, access token")

class MicrosoftRecoveryVerifyResponse(BaseModel):
    """Response for POST /auth/forgot-password/verify-microsoft"""
    ok: bool = True
    data: Dict[str, Any] = Field(..., description="Email and short-lived reset token")


class ManualSignupResponse(BaseModel):
    """Response for manual document-review signup flows."""
    ok: bool = True
    data: Dict[str, Any] = Field(..., description="Email, status, and confirmation message")


class RejectVerificationRequest(BaseModel):
    """Reject a verification submission with a required reason."""
    model_config = ConfigDict(extra='forbid')
    reason: str = Field(..., min_length=5, max_length=500, description="Reason shown to the student")

    @field_validator("reason")
    @classmethod
    def reason_must_be_valid(cls, v: str) -> str:
        value = v.strip()
        if not value:
            raise ValueError("Reason cannot be empty")
        if "<" in value or ">" in value or "script" in value.lower():
            raise ValueError("Reason contains invalid characters")
        return value
