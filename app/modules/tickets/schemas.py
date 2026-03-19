"""
Tickets Schemas

Pydantic models for ticket and ticket record requests and responses.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, time, datetime
from uuid import UUID


# ================================
# TICKET SCHEMAS
# ================================

class TicketResponse(BaseModel):
    """Single ticket response"""
    id: UUID
    merchant_name: str
    ticket_details: str
    pricing_period_start: date
    pricing_period_end: date
    market_price_adult: float
    our_price: float
    is_active: bool
    # Location & media (new columns)
    image_url: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TicketListResponse(BaseModel):
    """List of tickets response"""
    items: List[TicketResponse]
    total: int


# ================================
# TICKET RECORD SCHEMAS
# ================================

class TicketRecordResponse(BaseModel):
    """Single ticket record with joined ticket info"""
    id: UUID
    ticket_id: UUID
    user_id: UUID
    contact_name: str
    contact_email: str
    contact_phone: str
    visit_date: Optional[date] = None
    visit_time: Optional[time] = None
    quantity: int
    special_requests: Optional[str] = None
    unit_price: float
    total_price: float
    stripe_payment_intent_id: Optional[str] = None
    stripe_payment_status: str
    status: str
    e_ticket_url: Optional[str] = None
    fulfilled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    internal_notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    # Joined ticket fields
    merchant_name: Optional[str] = None
    ticket_details: Optional[str] = None

    class Config:
        from_attributes = True


class TicketRecordListResponse(BaseModel):
    """List of ticket records"""
    items: List[TicketRecordResponse]
    total: int


# ================================
# ADMIN UPDATE SCHEMAS
# ================================

class UpdateRecordStatusRequest(BaseModel):
    """Admin request to update a ticket record's status"""
    status: str = Field(
        ...,
        description="New status: pending | paid | processing | fulfilled | cancelled"
    )
    e_ticket_url: Optional[str] = Field(
        None,
        description="URL to the e-ticket (optional)"
    )
    internal_notes: Optional[str] = Field(
        None,
        description="Internal admin notes (optional)"
    )
    fulfilled_at: Optional[datetime] = Field(
        None,
        description="Timestamp of fulfillment; auto-set to now() when status=fulfilled if not provided"
    )
