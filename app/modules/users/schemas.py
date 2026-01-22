"""
Users Schemas

Pydantic models for user data.

NO BUSINESS LOGIC - Structure only
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
# from app.shared.enums import UserRole, UserStatus


class UserBase(BaseModel):
    """Base user fields"""
    email: EmailStr = Field(..., description="University email (IMMUTABLE)")
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    university: Optional[str] = None
    graduation_year: Optional[int] = None


class UserProfile(UserBase):
    """User profile response"""
    id: str = Field(..., description="User UUID from Supabase")
    role: str = Field(default="student")
    status: str = Field(default="active")
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None


class UpdateUserRequest(BaseModel):
    """Update user profile request (email NOT allowed)"""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    university: Optional[str] = None
    graduation_year: Optional[int] = Field(None, ge=2020, le=2030)
    
    # Email is IMMUTABLE - not included here


class CreateUserInternal(UserBase):
    """Internal schema for creating user (used by auth module)"""
    supabase_user_id: str = Field(..., description="UUID from Supabase Auth")
