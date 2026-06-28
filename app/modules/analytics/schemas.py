"""
Analytics Schemas

NO BUSINESS LOGIC - Structure only
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class TrackEventRequest(BaseModel):
    """Request to track analytics event"""
    event_type: str = Field(..., description="Event type from AnalyticsEventType enum")
    user_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class TrackEventResponse(BaseModel):
    """Response after tracking event"""
    success: bool = True
    message: str = "Event tracked successfully"


class UserStats(BaseModel):
    """User statistics"""
    user_id: str
    total_offers_viewed: int
    total_offers_claimed: int
    total_entitlements_redeemed: int
    total_savings: Optional[float] = None
    member_since: datetime
    last_activity: datetime


class PartnerStats(BaseModel):
    """Partner statistics"""
    partner_id: str
    partner_name: str
    total_offers: int
    active_offers: int
    total_claims: int
    total_redemptions: int
    conversion_rate: float
    period_start: datetime
    period_end: datetime
