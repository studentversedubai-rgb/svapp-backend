"""
SV Orbit LLM Presenter

Uses LLM to present activity plans in natural language.
LLM only formats/presents - does NOT generate offer data.

NO BUSINESS LOGIC - Structure only
"""

from typing import List, Dict


class LLMPresenter:
    """
    Uses LLM to present activity plans naturally
    
    IMPORTANT: LLM only formats presentation
    All offer data comes from retrieval (real data)
    """
    
    def __init__(self):
        """Initialize LLM client"""
        # TODO: Initialize OpenAI or other LLM client
        # TODO: Load from settings.OPENAI_API_KEY
        pass
    
    async def present_plan(
        self,
        intent: str,
        offers: List[Dict],
        user_preferences: Dict = None
    ) -> str:
        """
        Generate natural language presentation of plan
        
        LLM receives:
        - User intent
        - List of REAL offers (from retrieval)
        - User preferences
        
        LLM generates:
        - Natural language description
        - Suggested itinerary
        - Tips for using offers
        
        Args:
            intent: User's original intent
            offers: List of retrieved offers (REAL DATA)
            user_preferences: Optional user preferences
            
        Returns:
            Natural language plan presentation
        """
        # TODO: Construct prompt for LLM
        # TODO: Include all offer details
        # TODO: Request natural language presentation
        # TODO: Return formatted plan
        pass
    
    def _build_prompt(
        self,
        intent: str,
        offers: List[Dict],
        preferences: Dict = None
    ) -> str:
        """
        Build prompt for LLM
        
        Prompt should:
        - Clearly state user intent
        - List all offer details
        - Request natural presentation
        - Emphasize using ONLY provided offers
        
        Args:
            intent: User intent
            offers: Retrieved offers
            preferences: User preferences
            
        Returns:
            Formatted prompt
        """
        # TODO: Build structured prompt
        # TODO: Include instruction to use ONLY provided offers
        # TODO: Request specific format
        pass
    
    async def explain_offer_selection(
        self,
        offer: Dict,
        intent: str
    ) -> str:
        """
        Generate explanation for why offer was selected
        
        Args:
            offer: Offer details
            intent: User intent
            
        Returns:
            Natural language explanation
        """
        # TODO: Generate reasoning for offer inclusion
        pass
