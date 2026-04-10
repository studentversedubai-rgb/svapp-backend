"""
Merchant Validation Schemas

Request/response models for merchant-side validation endpoints.
These endpoints do NOT require student JWT authentication.
"""

from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime
from decimal import Decimal


class MerchantValidateRequest(BaseModel):
    """Request to validate a student's QR proof token"""
    proof_token: str = Field(..., description="QR proof token from student")


class MerchantValidateResponse(BaseModel):
    """Response from QR validation"""
    success: bool
    status: str  # PASS | FAIL
    reason: Optional[str] = None
    
    # Offer details (on PASS)
    entitlement_id: Optional[UUID] = None
    offer_title: Optional[str] = None
    offer_type: Optional[str] = None
    discount_value: Optional[str] = None
    merchant_name: Optional[str] = None
    student_name: Optional[str] = None
    original_price: Optional[Decimal] = None
    discounted_price: Optional[Decimal] = None


class MerchantVerifyPinRequest(BaseModel):
    """Request to verify merchant PIN before confirming a redemption"""
    proof_token: str = Field(..., description="QR proof token (used to look up the merchant)")
    merchant_pin: str = Field(..., min_length=4, description="Merchant PIN to verify")


class MerchantVerifyPinResponse(BaseModel):
    """Response from PIN verification"""
    success: bool
    message: str


class MerchantConfirmRequest(BaseModel):
    """Request to confirm redemption with bill amount"""
    proof_token: str = Field(..., description="QR proof token")
    merchant_pin: str = Field(..., min_length=4, max_length=6, description="Merchant PIN")
    total_bill_amount: Decimal = Field(..., gt=0, description="Total bill before discount")


class MerchantConfirmResponse(BaseModel):
    """Response from redemption confirmation"""
    success: bool
    message: str
    redemption_id: UUID
    entitlement_id: UUID
    total_bill: Decimal
    discount_amount: Decimal
    final_amount: Decimal
    savings: Decimal
    redeemed_at: datetime


class MerchantVoidRequest(BaseModel):
    """Request to void a redemption"""
    redemption_id: UUID = Field(..., description="Redemption to void")
    merchant_pin: str = Field(..., min_length=4, max_length=6, description="Merchant PIN")
    reason: str = Field(..., min_length=3, max_length=500, description="Void reason")


class MerchantVoidResponse(BaseModel):
    """Response from void operation"""
    success: bool
    message: str
    redemption_id: UUID
    voided_at: datetime
