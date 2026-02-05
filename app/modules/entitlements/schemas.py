"""
Entitlements Schemas - Phase 3

Pydantic models for entitlement and redemption requests/responses.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
from decimal import Decimal


# ================================
# CLAIM ENTITLEMENT
# ================================

class ClaimEntitlementRequest(BaseModel):
    """Request to claim an offer"""
    offer_id: str = Field(..., description="Offer UUID to claim")
    device_id: Optional[str] = Field(None, description="Device identifier for fraud prevention")


class ClaimEntitlementResponse(BaseModel):
    """Response after claiming offer"""
    success: bool = True
    message: str = "Entitlement claimed successfully"
    entitlement_id: str
    offer_id: str
    expires_at: datetime
    
    class Config:
        from_attributes = True


# ================================
# QR PROOF TOKEN GENERATION
# ================================

class GenerateProofRequest(BaseModel):
    """Request to generate QR proof token"""
    # No body needed - entitlement_id comes from path parameter
    pass


class GenerateProofResponse(BaseModel):
    """Response with proof token for QR code"""
    success: bool = True
    proof_token: str = Field(..., description="Short-lived token for QR code")
    expires_at: datetime = Field(..., description="Token expiry timestamp")
    ttl_seconds: int = Field(..., description="Time to live in seconds")
    
    class Config:
        from_attributes = True


# ================================
# VALIDATION (MERCHANT SIDE)
# ================================

class ValidateTokenRequest(BaseModel):
    """Request to validate proof token"""
    proof_token: str = Field(..., min_length=32, max_length=64, description="QR proof token or OTP fallback")


class ValidateTokenResponse(BaseModel):
    """Response after token validation"""
    success: bool
    status: str = Field(..., description="PASS or FAIL")
    reason: Optional[str] = Field(None, description="Failure reason if status is FAIL")
    
    # Offer details (only if PASS)
    entitlement_id: Optional[str] = None
    offer_title: Optional[str] = None
    offer_type: Optional[str] = None
    discount_value: Optional[str] = None
    merchant_name: Optional[str] = None
    student_name: Optional[str] = None
    
    class Config:
        from_attributes = True


# ================================
# AMOUNT CAPTURE & CONFIRMATION
# ================================

class ConfirmRedemptionRequest(BaseModel):
    """Request to confirm redemption with amount"""
    entitlement_id: str = Field(..., description="Entitlement UUID")
    total_bill_amount: Decimal = Field(..., gt=0, description="Total bill before discount")
    discounted_amount: Optional[Decimal] = Field(None, ge=0, description="Optional: Amount after discount")
    
    @field_validator('total_bill_amount', 'discounted_amount')
    @classmethod
    def validate_amounts(cls, v):
        """Ensure amounts have max 2 decimal places"""
        if v is not None:
            if v.as_tuple().exponent < -2:
                raise ValueError("Amount cannot have more than 2 decimal places")
        return v


class ConfirmRedemptionResponse(BaseModel):
    """Response after redemption confirmation"""
    success: bool = True
    message: str = "Redemption confirmed successfully"
    redemption_id: str
    entitlement_id: str
    
    # Financial summary
    total_bill: Decimal
    discount_amount: Decimal
    final_amount: Decimal
    savings: Decimal
    
    # Timestamps
    redeemed_at: datetime
    
    class Config:
        from_attributes = True


# ================================
# VOID LOGIC
# ================================

class VoidRedemptionRequest(BaseModel):
    """Request to void a redemption"""
    entitlement_id: str = Field(..., description="Entitlement UUID to void")
    reason: str = Field(..., min_length=10, max_length=500, description="Reason for voiding")


class VoidRedemptionResponse(BaseModel):
    """Response after voiding redemption"""
    success: bool = True
    message: str = "Redemption voided successfully"
    entitlement_id: str
    voided_at: datetime
    
    class Config:
        from_attributes = True


# ================================
# ENTITLEMENT DETAILS
# ================================

class EntitlementDetail(BaseModel):
    """Detailed entitlement view for student"""
    id: str
    offer_id: str
    offer_title: str
    offer_description: str
    offer_type: str
    discount_value: Optional[str] = None
    
    # Merchant info
    merchant_name: str
    merchant_logo_url: Optional[str] = None
    
    # State
    state: str
    
    # Timestamps
    claimed_at: datetime
    expires_at: datetime
    used_at: Optional[datetime] = None
    voided_at: Optional[datetime] = None
    
    # Can generate QR?
    can_redeem: bool = Field(..., description="Whether QR can be generated")
    
    class Config:
        from_attributes = True


class EntitlementListItem(BaseModel):
    """Entitlement in list view"""
    id: str
    offer_title: str
    merchant_name: str
    state: str
    claimed_at: datetime
    expires_at: datetime
    
    class Config:
        from_attributes = True


# ================================
# REDEMPTION HISTORY
# ================================

class RedemptionDetail(BaseModel):
    """Detailed redemption record"""
    id: str
    entitlement_id: str
    
    # Offer info
    offer_title: str
    offer_type: str
    merchant_name: str
    
    # Financial data
    total_bill_amount: Decimal
    discount_amount: Decimal
    final_amount: Decimal
    
    # Timestamps
    redeemed_at: datetime
    
    # Void status
    is_voided: bool
    voided_at: Optional[datetime] = None
    void_reason: Optional[str] = None
    
    class Config:
        from_attributes = True


# ================================
# ANALYTICS SCHEMAS
# ================================

class UserSavingsSummary(BaseModel):
    """User's total savings summary"""
    total_redemptions: int
    total_savings: Decimal
    total_spent: Decimal
    
    class Config:
        from_attributes = True


class MerchantRedemptionStats(BaseModel):
    """Merchant redemption statistics"""
    merchant_id: str
    merchant_name: str
    total_redemptions: int
    total_revenue: Decimal  # SV-attributed revenue
    total_discounts: Decimal
    
    class Config:
        from_attributes = True


class OfferRedemptionStats(BaseModel):
    """Offer-specific redemption statistics"""
    offer_id: str
    offer_title: str
    total_redemptions: int
    total_savings: Decimal
    
    class Config:
        from_attributes = True
