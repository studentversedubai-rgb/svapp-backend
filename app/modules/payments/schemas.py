"""
Payments Schemas

Pydantic models for mock order creation and related responses.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, time
from uuid import UUID


# ================================
# REQUEST SCHEMAS
# ================================

class CreateMockOrderRequest(BaseModel):
    """Request body to create a mock ticket order (test flow — no real payment)"""
    ticket_id: UUID = Field(..., description="ID of the ticket to purchase")
    quantity: int = Field(..., ge=1, description="Number of tickets (minimum 1)")
    visit_date: Optional[date] = Field(None, description="Desired visit date (optional)")
    visit_time: Optional[time] = Field(None, description="Desired visit time (optional)")
    contact_phone: str = Field(..., description="Contact phone number")
    special_requests: Optional[str] = Field(None, description="Any special requests (optional)")


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
