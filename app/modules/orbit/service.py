"""
SV Orbit Service

Orchestrates conversational AI-powered plan generation.
Uses conversation memory and intelligent intent detection.
"""

import logging
import uuid
from typing import List, Dict, Any, Optional
from app.core.config import Settings
from app.modules.orbit.retrieval import OfferRetrieval
from app.modules.orbit.llm import LLMPresenter
from app.modules.orbit.conversation import conversation_manager
from app.modules.orbit.schemas import OrbitChatResponse, OrbitOfferCard
from app.modules.orbit.distance import calculate_distance

logger = logging.getLogger(__name__)


class OrbitService:
    """
    Orchestrates conversational AI plan generation
    
    Flow:
    1. Load conversation history
    2. LLM analyzes intent (chat vs offers)
    3. Generate appropriate response
    4. Save to conversation history
    5. Return structured response
    """
    
    def __init__(self, settings: Settings = None):
        """Initialize with retrieval and LLM components"""
        if settings is None:
            settings = Settings()
        
        self.settings = settings
        self.retrieval = OfferRetrieval()
        self.llm = LLMPresenter(settings)
    
    async def chat(
        self,
        user_id: str,
        message: str,
        session_id: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None
    ) -> OrbitChatResponse:
        """
        Chat with Orbit AI assistant (conversational)
        
        Args:
            user_id: User UUID
            message: User's message
            session_id: Optional session ID for conversation continuity
            latitude: Optional user latitude for distance calculations
            longitude: Optional user longitude for distance calculations
            
        Returns:
            Orbit's response with recommended offers (if applicable)
        """
        try:
            # Generate session_id if not provided
            if not session_id:
                session_id = str(uuid.uuid4())
                logger.info(f"Generated new session: {session_id}")
            
            logger.info(f"Orbit chat request from user {user_id}, session {session_id}: {message}")
            if latitude and longitude:
                logger.info(f"User location: ({latitude}, {longitude})")
            
            # Step 1: Load conversation history
            history = conversation_manager.format_history_for_llm(user_id, session_id, limit=10)
            
            logger.debug(f"Loaded {len(history)} messages from history")
            
            # Step 2: Analyze intent using LLM
            intent_analysis = await self.llm.analyze_intent(message, history)
            
            intent = intent_analysis.get("intent", "offers")
            needs_retrieval = intent_analysis.get("needs_retrieval", True)
            
            logger.info(f"Intent: {intent}, Needs retrieval: {needs_retrieval}")
            
            # Initialize variables
            offers = []
            validated_plans = []
            
            # Step 3: Generate response based on intent
            if needs_retrieval and (intent == "offers" or intent == "offers_vague"):
                # User wants offers - retrieve and present
                
                # For vague requests, use broad search terms
                if intent == "offers_vague":
                    # Try to extract context or use popular categories
                    search_query = f"{message} food drinks entertainment"
                    logger.info(f"Vague request - using broad search: {search_query}")
                else:
                    search_query = message
                
                offers = await self.retrieval.retrieve_offers(
                    intent=search_query,
                    limit=self.settings.ORBIT_MAX_RESULTS
                )
                
                logger.info(f"Retrieved {len(offers)} offers from database")
                
                if offers:
                    # Generate response with offers using history
                    llm_response = await self.llm.generate_response_with_history(
                        user_message=message,
                        offers=offers,
                        conversation_history=history
                    )
                    
                    # Calculate distances if user location provided
                    if latitude and longitude:
                        for offer in offers:
                            merchant = offer.get('merchant')
                            if merchant and merchant.get('latitude') and merchant.get('longitude'):
                                distance = calculate_distance(
                                    latitude, longitude,
                                    merchant['latitude'], merchant['longitude']
                                )
                                offer['distance_km'] = distance
                            else:
                                offer['distance_km'] = None
                        
                        # Sort by distance (closest first)
                        offers.sort(key=lambda x: (x['distance_km'] is None, x.get('distance_km', float('inf'))))
                        logger.info(f"Sorted offers by distance from user")
                    
                    # Validate offer IDs and inject location data
                    validated_plans = self._validate_offer_ids(
                        llm_response.get("plans", []),
                        offers,
                        latitude,
                        longitude
                    )
                    
                    response_content = llm_response.get("content", "Here's what I found for you!")
                    
                else:
                    # No offers found
                    response_content = "Hmm, I couldn't find any offers matching that right now. 🤔 Want to try asking about something else? Like coffee, food, or entertainment?"
            
            else:
                # Pure conversation - no offers needed
                response_content = await self.llm.generate_conversation(message, history)
            
            # Step 4: Save messages to history
            conversation_manager.add_message(user_id, session_id, "user", message)
            conversation_manager.add_message(user_id, session_id, "assistant", response_content)
            
            # Step 5: Build and return response
            response = OrbitChatResponse(
                content=response_content,
                plans=validated_plans,
                session_id=session_id,
                metadata={
                    "intent": intent,
                    "total_retrieved": len(offers) if needs_retrieval else 0,
                    "total_recommended": len(validated_plans),
                    "conversation_length": conversation_manager.get_message_count(user_id, session_id)
                }
            )
            
            logger.info(f"Response generated: {len(validated_plans)} plans, intent={intent}")
            return response
            
        except Exception as e:
            logger.error(f"Error in Orbit chat: {e}", exc_info=True)
            # Return friendly error response
            return OrbitChatResponse(
                content="Oops! Something went wrong on my end. Can you try asking that again? 😅",
                plans=[],
                session_id=session_id or str(uuid.uuid4()),
                metadata={"error": str(e)}
            )
    
    def _validate_offer_ids(
        self,
        llm_plans: List[Dict],
        retrieved_offers: List[Dict],
        user_latitude: Optional[float] = None,
        user_longitude: Optional[float] = None
    ) -> List[OrbitOfferCard]:
        """
        Validate that LLM only used offer IDs from retrieved data
        AND inject real location data from database
        
        CRITICAL: This prevents hallucinations
        
        Args:
            llm_plans: Plans returned by LLM
            retrieved_offers: Offers retrieved from database
            user_latitude: User's latitude for distance calculation
            user_longitude: User's longitude for distance calculation
            
        Returns:
            Validated offer cards with real location data
        """
        # Build map of valid offers by ID
        offers_by_id = {offer.get('id'): offer for offer in retrieved_offers}
        
        validated_plans = []
        for plan in llm_plans:
            offer_id = plan.get('id')
            
            # Only include if ID exists in retrieved offers
            if offer_id in offers_by_id:
                try:
                    # Get real offer data from database
                    real_offer = offers_by_id[offer_id]
                    merchant = real_offer.get('merchant', {})
                    
                    # Inject REAL location data from database
                    # LLM should NOT fabricate this data
                    plan['merchant_name'] = merchant.get('name', 'Unknown')
                    plan['address'] = merchant.get('address')
                    plan['latitude'] = merchant.get('latitude')
                    plan['longitude'] = merchant.get('longitude')
                    
                    # Calculate distance if user location and merchant location available
                    if (user_latitude and user_longitude and 
                        merchant.get('latitude') and merchant.get('longitude')):
                        plan['distance_km'] = calculate_distance(
                            user_latitude, user_longitude,
                            merchant['latitude'], merchant['longitude']
                        )
                    else:
                        plan['distance_km'] = real_offer.get('distance_km')
                    
                    validated_plans.append(OrbitOfferCard(**plan))
                except Exception as e:
                    logger.warning(f"Failed to validate plan: {e}")
                    continue
            else:
                logger.warning(f"LLM hallucinated offer ID: {offer_id}")
        
        logger.info(f"Validated {len(validated_plans)}/{len(llm_plans)} plans")
        return validated_plans
    
    async def generate_plan(
        self,
        user_id: str,
        intent: str,
        preferences: Dict[str, Any] = None,
        budget: float = None,
        location: str = None
    ) -> dict:
        """
        Generate activity plan (Legacy method)
        
        Redirects to chat method
        """
        response = await self.chat(user_id, intent)
        return response.dict()
    
    async def get_plan(self, plan_id: str) -> dict:
        """Get saved plan (Not implemented yet)"""
        raise NotImplementedError("Plan storage not yet implemented")
    
    async def submit_feedback(
        self,
        plan_id: str,
        rating: int,
        was_helpful: bool,
        comments: str = None,
        used_offers: List[str] = None
    ):
        """Store plan feedback (Not implemented yet)"""
        raise NotImplementedError("Feedback storage not yet implemented")
    
    def score_offers(
        self,
        offers: List[dict],
        intent: str,
        preferences: Dict[str, Any] = None
    ) -> List[dict]:
        """Score offers (handled by retrieval layer)"""
        return offers