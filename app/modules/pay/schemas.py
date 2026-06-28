"""
SV Pay Schemas

NO BUSINESS LOGIC - Structure only
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class InitiatePaymentRequest(BaseModel):
    """Request to initiate payment"""
    amount: float = Field(..., gt=0, description="Payment amount")
    currency: str = Field(default="AED", description="Currency code")
    description: Optional[str] = None
    metadata: Optional[dict] = None


class PaymentResponse(BaseModel):
    """Payment initiation response"""
    transaction_id: str
    payment_url: Optional[str] = None
    payment_token: Optional[str] = None
    status: str
    amount: float
    currency: str
    created_at: datetime


class Transaction(BaseModel):
    """Payment transaction"""
    id: str
    user_id: str
    amount: float
    currency: str
    status: str
    description: Optional[str] = None
    payment_method: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class WebhookEvent(BaseModel):
    """Payment webhook event"""
    event_type: str
    transaction_id: str
    status: str
    metadata: Optional[dict] = None
