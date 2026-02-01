"""
Offers Schemas - Phase 2

Pydantic models for offer requests and responses.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime, time


# ================================
# CATEGORY SCHEMAS
# ================================

class CategoryResponse(BaseModel):
    """Category response"""
    id: str
    name: str
    slug: str
    description: Optional[str] = None
    icon_url: Optional[str] = None
    sort_order: int = 0
    
    class Config:
        from_attributes = True


# ================================
# MERCHANT SCHEMAS
# ================================

class MerchantBasic(BaseModel):
    """Basic merchant info for offer listings"""
    id: str
    name: str
    logo_url: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    
    class Config:
        from_attributes = True


class MerchantDetail(MerchantBasic):
    """Detailed merchant info"""
    description: Optional[str] = None
    address: Optional[str] = None
    
    class Config:
        from_attributes = True


# ================================
# OFFER SCHEMAS
# ================================

class OfferListItem(BaseModel):
    """Offer in list view (home feed, search results)"""
    id: str
    title: str
    description: str
    merchant: MerchantBasic
    category: Optional[CategoryResponse] = None
    
    # Offer details
    offer_type: str
    discount_value: Optional[str] = None
    original_price: Optional[float] = None
    discounted_price: Optional[float] = None
    
    # Media
    image_url: Optional[str] = None
    
    # Validity
    valid_from: datetime
    valid_until: datetime
    
    # Optional: distance if location provided
    distance_km: Optional[float] = None
    
    # Featured flag
    is_featured: bool = False
    
    # Timestamps
    created_at: datetime
    
    class Config:
        from_attributes = True


class OfferDetail(BaseModel):
    """Detailed offer view"""
    id: str
    title: str
    description: str
    terms_conditions: Optional[str] = None
    
    # Merchant details
    merchant: MerchantDetail
    category: Optional[CategoryResponse] = None
    
    # Offer details
    offer_type: str
    discount_value: Optional[str] = None
    original_price: Optional[float] = None
    discounted_price: Optional[float] = None
    
    # Media
    image_url: Optional[str] = None
    images: Optional[List[str]] = None
    
    # Validity
    valid_from: datetime
    valid_until: datetime
    time_valid_from: Optional[time] = None
    time_valid_until: Optional[time] = None
    valid_days_of_week: Optional[List[int]] = None
    
    # Claiming info
    max_claims_per_user: Optional[int] = None
    total_claims: int = 0
    max_total_claims: Optional[int] = None
    
    # Featured flag
    is_featured: bool = False
    
    # Optional: distance if location provided
    distance_km: Optional[float] = None
    
    # Timestamps
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# ================================
# REQUEST SCHEMAS
# ================================

class HomeFeedRequest(BaseModel):
    """Request for home feed with optional location"""
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    
    @field_validator('latitude', 'longitude')
    @classmethod
    def validate_location(cls, v, info):
        """Both lat and lon must be provided together"""
        # This will be validated in the service layer
        return v


class SearchRequest(BaseModel):
    """Search offers request"""
    query: Optional[str] = Field(None, max_length=200)
    category_id: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    radius_km: Optional[float] = Field(None, ge=0, le=50)  # Max 50km radius
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    
    @field_validator('query')
    @classmethod
    def sanitize_query(cls, v):
        """Sanitize search query"""
        if v:
            # Remove potentially harmful characters
            v = v.strip()
            # Basic sanitization - remove SQL-like characters
            dangerous_chars = [';', '--', '/*', '*/', 'xp_', 'sp_', 'DROP', 'DELETE', 'INSERT', 'UPDATE']
            v_upper = v.upper()
            for char in dangerous_chars:
                if char in v_upper:
                    raise ValueError("Invalid search query")
        return v


class NearbyOffersRequest(BaseModel):
    """Request for nearby offers"""
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_km: float = Field(5.0, ge=0.1, le=50)  # Default 5km, max 50km
    category_id: Optional[str] = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


# ================================
# RESPONSE SCHEMAS
# ================================

class PaginatedOffersResponse(BaseModel):
    """Paginated offers response"""
    items: List[OfferListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class CategoriesResponse(BaseModel):
    """List of categories"""
    categories: List[CategoryResponse]
