"""
Offers Schemas

NO BUSINESS LOGIC - Structure only
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
# from app.shared.enums import OfferCategory, OfferType


class OfferBase(BaseModel):
    """Base offer fields"""
    title: str
    description: str
    partner_id: str
    partner_name: str
    category: str
    offer_type: str
    discount_value: Optional[str] = None
    terms_conditions: str
    valid_from: datetime
    valid_until: datetime
    image_url: Optional[str] = None


class OfferListItem(OfferBase):
    """Offer in list view"""
    id: str
    is_active: bool
    total_claims: int


class OfferDetail(OfferBase):
    """Detailed offer view"""
    id: str
    is_active: bool
    total_claims: int
    max_claims_per_user: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class ClaimOfferResponse(BaseModel):
    """Response after claiming offer"""
    success: bool = True
    message: str
    entitlement_id: str
    offer_id: str
