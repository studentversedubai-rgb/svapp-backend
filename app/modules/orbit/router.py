"""
SV Orbit Router

AI-powered activity planner for students.

IMPORTANT CONSTRAINTS:
- Retrieval-only (no hallucinated data)
- Only suggests partner offers
- Uses scoring + orchestration + LLM presentation

Endpoints:
- POST /orbit/chat: Chat with Orbit AI
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_user
from app.core.config import Settings
from app.modules.orbit.schemas import (
    OrbitChatRequest,
    OrbitChatResponse
)
from app.modules.orbit.service import OrbitService

router = APIRouter()
logger = logging.getLogger(__name__)


# Initialize settings
settings = Settings()


# Feature flag check
if not settings.FEATURE_SV_ORBIT_ENABLED:
    logger.warning("SV Orbit feature is disabled")


@router.post("/chat", response_model=OrbitChatResponse)
async def orbit_chat(
    request: OrbitChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Chat with Orbit AI assistant
    
    Orbit uses RAG (Retrieval-Augmented Generation) to recommend real offers:
    - Retrieves offers from database (no hallucinations)
    - Uses LLM for natural, witty presentation
    
    **Two-Layer Architecture:**
    1. **Retrieval Layer**: Queries database for relevant offers
    2. **Generation Layer**: LLM selects best 3 and formats response
    
    Args:
        request: User's message to Orbit
        current_user: Authenticated user (injected)
    
    Returns:
        Orbit's response with recommended offers
        
    Raises:
        HTTPException: 500 if service error occurs
    """
    try:
        # Check feature flag
        if not settings.FEATURE_SV_ORBIT_ENABLED:
            raise HTTPException(
                status_code=503,
                detail="Orbit is currently unavailable"
            )
        
        # Initialize service
        service = OrbitService(settings)
        
        # Get response from Orbit (service handles session_id generation if needed)
        response = await service.chat(
            user_id=current_user["id"],
            message=request.message,
            session_id=request.session_id
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in orbit chat: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Something went wrong with Orbit. Please try again! 😅"
        )
