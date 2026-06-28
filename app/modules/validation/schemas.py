"""
Validation Schemas

NO BUSINESS LOGIC - Structure only
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ScanQRRequest(BaseModel):
    """Request to scan QR code"""
    qr_data: str = Field(..., description="QR code data")


class ScanQRResponse(BaseModel):
    """Response after scanning QR code"""
    success: bool
    entitlement_id: str
    offer_title: str
    student_name: str
    student_email: str
    reserved_at: datetime
    expires_at: datetime
    is_valid: bool
    message: str


class RedeemRequest(BaseModel):
    """Request to confirm redemption"""
    entitlement_id: str
    validator_id: str
    notes: Optional[str] = None


class RedeemResponse(BaseModel):
    """Response after redemption"""
    success: bool = True
    message: str
    entitlement_id: str
    redeemed_at: datetime


class ValidationHistoryItem(BaseModel):
    """Single validation history entry"""
    entitlement_id: str
    offer_title: str
    student_name: str
    redeemed_at: datetime
    notes: Optional[str] = None
