"""
SV Orbit Schemas
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


# ================================
# CHAT SCHEMAS (New)
# ================================

class OrbitChatRequest(BaseModel):
    """Request for Orbit chat endpoint"""
    message: str = Field(..., min_length=1, max_length=500, description="User's message to Orbit")
    session_id: Optional[str] = Field(None, description="Session ID for conversation continuity")
    latitude: Optional[float] = Field(None, ge=-90, le=90, description="User's latitude for distance calculation")
    longitude: Optional[float] = Field(None, ge=-180, le=180, description="User's longitude for distance calculation")


class OrbitOfferCard(BaseModel):
    """Offer card in Orbit response"""
    id: str
    title: str
    description: str
    merchant_name: str = Field(..., description="Merchant/partner name")
    address: Optional[str] = Field(None, description="Merchant address")
    latitude: Optional[float] = Field(None, description="Merchant latitude")
    longitude: Optional[float] = Field(None, description="Merchant longitude")
    distance_km: Optional[float] = Field(None, description="Distance from user in kilometers")
    tags: Dict[str, Any] = Field(default_factory=dict)
    highlights: List[str] = Field(default_factory=list)


class OrbitChatResponse(BaseModel):
    """Response from Orbit chat"""
    content: str = Field(..., description="Orbit's intro message")
    plans: List[OrbitOfferCard] = Field(default_factory=list)
    session_id: Optional[str] = Field(None, description="Session ID for conversation tracking")
    metadata: Optional[Dict[str, Any]] = None


# ================================
# PLAN SCHEMAS (Legacy)
# ================================


class GeneratePlanRequest(BaseModel):
    """Request to generate activity plan"""
    intent: str = Field(..., description="User's intent (e.g., 'date night', 'study break')")
    preferences: Optional[Dict[str, Any]] = None
    budget: Optional[float] = None
    location: Optional[str] = None


class PlanOffer(BaseModel):
    """Offer included in plan"""
    offer_id: str
    title: str
    partner_name: str
    category: str
    description: str
    relevance_score: float
    reasoning: str = Field(..., description="Why this offer was included")


class PlanResponse(BaseModel):
    """Generated plan response"""
    plan_id: str
    user_id: str
    intent: str
    offers: List[PlanOffer]
    presentation: str = Field(..., description="LLM-generated natural language presentation")
    total_estimated_savings: Optional[float] = None
    created_at: datetime
    status: str = "active"


class PlanFeedbackRequest(BaseModel):
    """Feedback on generated plan"""
    plan_id: str
    rating: int = Field(..., ge=1, le=5, description="1-5 star rating")
    was_helpful: bool
    comments: Optional[str] = None
    used_offers: Optional[List[str]] = Field(None, description="List of offer IDs user actually used")


class PlanFeedbackResponse(BaseModel):
    """Response after submitting feedback"""
    success: bool = True
    message: str = "Thank you for your feedback!"
