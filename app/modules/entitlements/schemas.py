"""
Entitlements Schemas

NO BUSINESS LOGIC - Structure only
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
# from app.shared.enums import EntitlementState


class EntitlementBase(BaseModel):
    """Base entitlement fields"""
    user_id: str
    offer_id: str
    state: str
    redemption_method: str


class EntitlementListItem(EntitlementBase):
    """Entitlement in list view"""
    id: str
    offer_title: str
    partner_name: str
    claimed_at: datetime
    expires_at: Optional[datetime] = None


class EntitlementDetail(EntitlementBase):
    """Detailed entitlement view"""
    id: str
    offer_title: str
    offer_description: str
    partner_name: str
    qr_code: Optional[str] = None  # Base64 encoded QR code
    redemption_code: Optional[str] = None
    claimed_at: datetime
    reserved_at: Optional[datetime] = None
    redeemed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    validator_id: Optional[str] = None


class ReserveEntitlementResponse(BaseModel):
    """Response after reserving entitlement"""
    success: bool = True
    message: str
    entitlement_id: str
    qr_code: str
    expires_in_minutes: int


class RedeemEntitlementRequest(BaseModel):
    """Request to redeem entitlement"""
    validator_id: str
    notes: Optional[str] = None


class RedeemEntitlementResponse(BaseModel):
    """Response after redeeming"""
    success: bool = True
    message: str
    entitlement_id: str
    redeemed_at: datetime
