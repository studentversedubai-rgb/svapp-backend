"""
Online Deals Schemas

Pydantic models for online deal requests and responses.
"""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ================================
# ENUMS
# ================================

class OnlineDealType(str, Enum):
    DISCOUNT_CODE = "discount_code"
    AFFILIATE_LINK = "affiliate_link"


# ================================
# RESPONSE SCHEMAS
# ================================

class OnlineDealListItem(BaseModel):
    """Online deal in list view"""
    id: str
    type: OnlineDealType
    brand: str
    category: str
    title: str
    discount: str
    description: Optional[str] = None
    image: str
    brand_color: Optional[str] = None
    highlights: Optional[List[str]] = None
    isOnline: bool = True  # Flag for frontend routing
    is_active: bool = True
    created_at: datetime
    
    class Config:
        from_attributes = True


class OnlineDealDetail(BaseModel):
    """Detailed online deal view"""
    id: str
    type: OnlineDealType
    brand: str
    category: str
    title: str
    discount: str
    description: Optional[str] = None
    image: str
    brand_color: Optional[str] = None
    highlights: Optional[List[str]] = None
    terms: Optional[List[str]] = None
    discount_code: Optional[str] = None  # Only for discount_code type
    redemption_url: str
    isOnline: bool = True
    is_active: bool = True
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# ================================
# REQUEST SCHEMAS
# ================================

class OnlineDealsListRequest(BaseModel):
    """Request for listing online deals"""
    model_config = ConfigDict(extra='forbid')
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    category: Optional[str] = None  # Filter by category


class OnlineDealCreateRequest(BaseModel):
    """Request for creating an online deal (Admin only)"""
    model_config = ConfigDict(extra='forbid')
    type: OnlineDealType
    brand: str = Field(..., min_length=1, max_length=255)
    category: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=500)
    discount: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    image: str = Field(..., min_length=1)
    brand_color: Optional[str] = Field(None, pattern=r'^[0-9A-Fa-f]{6}$')
    highlights: Optional[List[str]] = None
    terms: Optional[List[str]] = None
    discount_code: Optional[str] = None
    redemption_url: str = Field(..., min_length=1)
    is_active: bool = True
    is_featured: bool = False
    
    @field_validator('discount_code')
    @classmethod
    def validate_discount_code(cls, v, info):
        """Discount code required for discount_code type"""
        # Will be validated at service level
        return v


class OnlineDealUpdateRequest(BaseModel):
    """Request for updating an online deal (Admin only)"""
    model_config = ConfigDict(extra='forbid')
    type: Optional[OnlineDealType] = None
    brand: Optional[str] = Field(None, min_length=1, max_length=255)
    category: Optional[str] = Field(None, min_length=1, max_length=100)
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    discount: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    image: Optional[str] = None
    brand_color: Optional[str] = Field(None, pattern=r'^[0-9A-Fa-f]{6}$')
    highlights: Optional[List[str]] = None
    terms: Optional[List[str]] = None
    discount_code: Optional[str] = None
    redemption_url: Optional[str] = None
    is_active: Optional[bool] = None
    is_featured: Optional[bool] = None


# ================================
# RESPONSE SCHEMAS
# ================================

class PaginatedOnlineDealsResponse(BaseModel):
    """Paginated online deals response"""
    items: List[OnlineDealListItem]
    total: int
    page: int
    page_size: int
    total_pages: int
