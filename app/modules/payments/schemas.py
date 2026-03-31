"""
Payments Schemas

Pydantic models for mock order creation and related responses.
"""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional
from datetime import date, time
from uuid import UUID
import re


# ================================
# REQUEST SCHEMAS
# ================================

class CreateMockOrderRequest(BaseModel):
    """Request body to create a mock ticket order (test flow — no real payment)"""
    model_config = ConfigDict(extra='forbid')
    
    ticket_id: UUID = Field(..., description="ID of the ticket to purchase")
    quantity: int = Field(..., ge=1, le=20, description="Number of tickets (minimum 1, max 20)")
    visit_date: Optional[date] = Field(None, description="Desired visit date (optional)")
    visit_time: Optional[time] = Field(None, description="Desired visit time (optional)")
    contact_phone: str = Field(..., max_length=20, description="Contact phone number")
    contact_email: str = Field(..., description="Personal email to send tickets to")
    special_requests: Optional[str] = Field(None, max_length=500, description="Any special requests (optional)")

    @field_validator("contact_phone")
    @classmethod
    def phone_must_be_valid(cls, v: str) -> str:
        v = v.strip().replace(" ", "")
        if not re.match(r"^\+?[1-9]\d{1,14}$", v):
            raise ValueError("Phone number must be in international format (e.g. +971501234567)")
        return v

    @field_validator("visit_date")
    @classmethod
    def date_must_not_be_past(cls, v: Optional[date]) -> Optional[date]:
        if v and v < date.today():
            raise ValueError("Visit date cannot be in the past")
        return v

    @field_validator("special_requests", mode="before")
    @classmethod
    def strip_html_and_scripts(cls, v: Optional[str]) -> Optional[str]:
        if v and isinstance(v, str):
            if "<" in v or ">" in v or "script" in v.lower() or "javascript:" in v.lower():
                raise ValueError("Input contains invalid or dangerous characters")
        return v


# ================================
# RESPONSE SCHEMAS
# ================================

class CreateMockOrderResponse(BaseModel):
    """Response after creating a mock ticket order"""
    record_id: UUID = Field(..., description="Created ticket_records row ID")
    mock_payment_intent_id: str = Field(..., description="Fake payment intent ID (mock_pi_...)")
    total_price: float = Field(..., description="Total price in AED")
    status: str = Field(..., description="Payment status — always 'paid' in mock flow")
    message: str = Field(..., description="Informational message about the mock flow")

class CreatePaymentIntentRequest(CreateMockOrderRequest):
    """Request body to create a Stripe Payment Intent"""
    pass

class CreatePaymentIntentResponse(BaseModel):
    """Response after creating a Stripe Payment Intent"""
    payment_intent_client_secret: str = Field(..., description="Stripe client secret")
    ephemeral_key_secret: str = Field(..., description="Stripe ephemeral key secret")
    customer_id: str = Field(..., description="Stripe customer ID")
    record_id: UUID = Field(..., description="Created ticket_records row ID")
    total_price: float = Field(..., description="Total price in AED")
    currency: str = Field(..., description="Currency, e.g. 'aed'")

class ConfirmPaymentRequest(BaseModel):
    """Request body to confirm a payment"""
    record_id: UUID = Field(..., description="ID of the booking record")
    payment_intent_id: str = Field(..., description="Stripe PaymentIntent ID")

class ConfirmPaymentResponse(BaseModel):
    """Response after confirming a payment"""
    record_id: UUID = Field(..., description="ID of the booking record")
    status: str = Field(..., description="Status, e.g., 'confirmed'")
    message: str = Field(..., description="Message")
