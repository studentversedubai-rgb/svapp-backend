"""
SV Orbit Router

AI-powered activity planner for students.

IMPORTANT CONSTRAINTS:
- Retrieval-only (no hallucinated data)
- Only suggests partner offers
- Uses scoring + orchestration + LLM presentation

Endpoints:
- POST /orbit/plans: Generate activity plan
- GET /orbit/plans/{plan_id}: Get saved plan
- POST /orbit/plans/{plan_id}/feedback: Submit feedback on plan

NO BUSINESS LOGIC - Structure only
"""

from fastapi import APIRouter, Depends
# from app.core.security import get_current_user
# from app.core.config import settings
# from app.modules.orbit.schemas import (
#     GeneratePlanRequest,
#     PlanResponse,
#     PlanFeedbackRequest
# )
# from app.modules.orbit.service import OrbitService

router = APIRouter()


# Feature flag check
# if not settings.FEATURE_SV_ORBIT_ENABLED:
#     # Router is disabled via feature flag
#     pass


@router.post("/plans")
async def generate_plan():
    """
    Generate AI-powered activity plan
    
    Steps:
    1. Parse user intent (e.g., "date night", "study session")
    2. Retrieve relevant partner offers (retrieval-only)
    3. Score offers based on relevance
    4. Orchestrate plan with multiple offers
    5. Use LLM to present plan in natural language
    
    Returns:
        Generated plan with partner offers
    """
    # TODO: Implement plan generation
    # TODO: Use retrieval service to get offers
    # TODO: Use scoring to rank offers
    # TODO: Use LLM to format presentation
    pass


@router.get("/plans/{plan_id}")
async def get_plan():
    """
    Get saved plan by ID
    
    Returns:
        Previously generated plan
    """
    # TODO: Retrieve plan from database
    pass


@router.post("/plans/{plan_id}/feedback")
async def submit_plan_feedback():
    """
    Submit feedback on generated plan
    
    Used to improve future recommendations
    
    Returns:
        Success confirmation
    """
    # TODO: Store feedback
    # TODO: Use for improving scoring algorithm
    pass
