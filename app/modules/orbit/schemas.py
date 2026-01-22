"""
SV Orbit Schemas

NO BUSINESS LOGIC - Structure only
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


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
