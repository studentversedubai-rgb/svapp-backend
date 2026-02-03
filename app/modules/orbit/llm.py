"""
SV Orbit LLM Presenter

Uses LLM to present activity plans in natural language.
LLM only formats/presents - does NOT generate offer data.
"""

import json
import logging
from typing import List, Dict
from openai import OpenAI
from app.core.config import Settings

logger = logging.getLogger(__name__)


class LLMPresenter:
    """
    Uses LLM to present activity plans naturally
    
    IMPORTANT: LLM only formats presentation
    All offer data comes from retrieval (real data)
    """
    
    def __init__(self, settings: Settings):
        """Initialize OpenRouter client"""
        self.settings = settings
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY,
        )
        self.model = settings.OPENROUTER_MODEL
    
    async def generate_response(
        self,
        user_message: str,
        offers: List[Dict]
    ) -> dict:
        """
        Generate natural language response with offer recommendations
        
        LLM receives:
        - User message
        - List of REAL offers (from retrieval)
        
        LLM generates:
        - Natural language intro
        - Selection of best 3 offers
        - Structured JSON response
        
        Args:
            user_message: User's original message
            offers: List of retrieved offers (REAL DATA)
            
        Returns:
            Structured response with content and plans
        """
        try:
            # Build prompts
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(user_message, offers)
            
            # Call OpenRouter API
            logger.info(f"Calling OpenRouter with model: {self.model}")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            
            # Extract response content
            llm_response = response.choices[0].message.content
            logger.info(f"Received LLM response: {llm_response[:100]}...")
            
            # Parse JSON response
            parsed_response = self._parse_llm_response(llm_response)
            
            return parsed_response
            
        except Exception as e:
            logger.error(f"Error generating LLM response: {e}")
            raise
    
    def _build_system_prompt(self) -> str:
        """
        Build system prompt for Orbit personality
        
        Returns:
            System prompt string
        """
        return """You are Orbit, a witty and fun local guide for students in Dubai. 
You speak in a trendy, slightly Gen-Z but helpful tone. You're enthusiastic about helping students discover amazing deals.

CRITICAL RULES:
1. NEVER invent or hallucinate offers. Only use the Context Data provided.
2. Select EXACTLY 3 offers from the Context Data that best match the user's request.
3. Return ONLY valid JSON - no markdown, no code blocks, no extra text.
4. Use offer IDs EXACTLY as provided in the Context Data.
5. Keep your intro message fun but concise (2-3 sentences max).

Your personality: Helpful, witty, enthusiastic, slightly playful but professional."""
    
    def _build_user_prompt(
        self,
        message: str,
        offers: List[Dict]
    ) -> str:
        """
        Build user prompt with context
        
        Args:
            message: User's message
            offers: Retrieved offers
            
        Returns:
            Formatted user prompt
        """
        # Format offers as simplified JSON for context
        offers_context = []
        for offer in offers:
            merchant = offer.get('merchant', {})
            category = offer.get('category', {})
            
            offers_context.append({
                "id": offer.get('id'),
                "title": offer.get('title'),
                "description": offer.get('description'),
                "merchant_name": merchant.get('name', 'Unknown'),
                "category": category.get('name', 'General'),
                "discount_value": offer.get('discount_value', ''),
                "original_price": offer.get('original_price'),
                "discounted_price": offer.get('discounted_price')
            })
        
        offers_json = json.dumps(offers_context, indent=2)
        
        prompt = f"""User Query: "{message}"

Context Data (Real Database Results):
{offers_json}

Task:
1. Select the best 3 offers from the Context Data above that match the User Query.
2. Write a fun, engaging intro message (2-3 sentences).
3. Return ONLY a JSON object in this EXACT format (no markdown, no code blocks):

{{
  "content": "Your fun intro text here...",
  "plans": [
     {{
       "id": "OFFER_ID_FROM_CONTEXT",
       "title": "Merchant Name",
       "description": "Offer Title (e.g., 50% Off Coffee)",
       "tags": {{"budget": "$", "time": "Open Now", "dietary": []}},
       "highlights": ["50% OFF", "Student Friendly"]
     }}
  ]
}}

Remember: Use ONLY offer IDs from the Context Data above. Return clean JSON only."""
        
        return prompt
    
    def _parse_llm_response(self, response: str) -> dict:
        """
        Parse and validate LLM JSON response
        
        Args:
            response: Raw LLM response
            
        Returns:
            Parsed and validated response dict
        """
        try:
            # Remove markdown code blocks if present
            cleaned = response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            
            # Parse JSON
            parsed = json.loads(cleaned)
            
            # Validate required fields
            if "content" not in parsed:
                raise ValueError("LLM response missing 'content' field")
            if "plans" not in parsed:
                raise ValueError("LLM response missing 'plans' field")
            
            # Ensure plans is a list
            if not isinstance(parsed["plans"], list):
                parsed["plans"] = []
            
            logger.info(f"Successfully parsed LLM response with {len(parsed['plans'])} plans")
            return parsed
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.error(f"Raw response: {response}")
            # Return fallback response
            return {
                "content": "I found some offers but had trouble formatting them. Let me try again!",
                "plans": []
            }
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            raise
    
    async def present_plan(
        self,
        intent: str,
        offers: List[Dict],
        user_preferences: Dict = None
    ) -> str:
        """
        Generate natural language presentation of plan
        
        (Legacy method for compatibility)
        
        Args:
            intent: User's original intent
            offers: List of REAL offers (from retrieval)
            user_preferences: Optional user preferences
            
        Returns:
            Natural language plan presentation
        """
        response = await self.generate_response(intent, offers)
        return response.get("content", "")
    
    async def analyze_intent(
        self,
        user_message: str,
        conversation_history: List[Dict[str, str]]
    ) -> Dict[str, any]:
        """
        Analyze user's intent: Are they chatting or requesting offers?
        
        Uses LLM to intelligently determine context.
        
        Args:
            user_message: Current user message
            conversation_history: Previous messages in OpenAI format
            
        Returns:
            {
              "intent": "chat"|"offers",
              "needs_retrieval": bool,
              "confidence": float
            }
        """
        try:
            system_prompt = """You are a specialized intent classifier. Your ONLY job is to output valid JSON.

Classify the user's message into ONE category:

1. CHAT: Pure greetings, questions about you (NO request for recommendations)
   - "hi", "hello", "how are you", "who are you", "thanks"
   
2. OFFERS: Specific requests for products/services
   - "coffee", "burger", "show me gym", "I want pizza", "sushi place"

3. OFFERS_VAGUE: Want recommendations but no specifics (celebrations, general requests)
   - "I want to celebrate", "surprise me", "show me something", "what do you recommend", "I'm hungry"

CRITICAL RULES:
- Output ONLY JSON, no other text
- No explanations, no conversational responses
- Just the classification JSON

Output format:
{"intent": "chat", "needs_retrieval": false, "confidence": 0.95}
or
{"intent": "offers", "needs_retrieval": true, "confidence": 0.9}
or
{"intent": "offers_vague", "needs_retrieval": true, "confidence": 0.85}"""

            # Build a simple message for classification
            user_prompt = f"Classify this message: \"{user_message}\""
            
            # Call LLM with JSON mode if supported
            try:
                # Try with response_format for JSON mode
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.1,  # Extremely low for consistent output
                    max_tokens=50,
                    response_format={"type": "json_object"}  # Force JSON mode
                )
            except:
                # Fallback without JSON mode
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.1,
                    max_tokens=50
                )
            
            content = response.choices[0].message.content.strip()
            
            logger.debug(f"Intent analysis raw response: {content}")
            
            # Clean up response - remove markdown code blocks if present
            if content.startswith("```"):
                content = content.replace("```json", "").replace("```", "").strip()
            
            # Parse JSON
            result = json.loads(content)
            
            logger.info(f"Intent classified: {result['intent']} (confidence: {result.get('confidence', 'N/A')})")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Intent analysis JSON parsing failed: {e}. Raw: {content if 'content' in locals() else 'N/A'}")
            
            # Fallback: Simple keyword matching
            message_lower = user_message.lower().strip()
            
            # Check for greetings and small talk
            greeting_patterns = ["hi", "hello", "hey", "yo", "sup", "what's up", "whats up", 
                               "how are you", "how r u", "thanks", "thank you", "who are you"]
            
            # Check for vague offer requests (wants something but not specific)
            vague_patterns = ["celebrate", "recommendation", "recommend", "surprise me", 
                            "show me something", "what do you have", "i'm hungry", "im hungry",
                            "looking for something", "want something", "any suggestions"]
            
            # Check for specific service/product keywords  
            offer_patterns = ["coffee", "burger", "pizza", "gym", "food", "drink", "restaurant",
                            "sushi", "pasta", "fitness", "cinema", "movie", "spa"]
            
            # Check greetings first (pure chat, no offers wanted)
            if any(word in message_lower for word in greeting_patterns) and len(message_lower) < 30:
                logger.info("Fallback: Detected greeting")
                return {"intent": "chat", "needs_retrieval": False, "confidence": 0.85}
            
            # Check for vague offer requests
            if any(phrase in message_lower for phrase in vague_patterns):
                logger.info("Fallback: Detected vague offer request")
                return {"intent": "offers_vague", "needs_retrieval": True, "confidence": 0.8}
            
            # Check for specific offers
            if any(word in message_lower for word in offer_patterns):
                logger.info("Fallback: Detected specific offer request")
                return {"intent": "offers", "needs_retrieval": True, "confidence": 0.75}
            
            # If contains "want", "need", "looking" but no specific product - vague
            if any(word in message_lower for word in ["want", "need", "looking"]):
                logger.info("Fallback: Detected vague want/need")
                return {"intent": "offers_vague", "needs_retrieval": True, "confidence": 0.7}
            
            # If short message (< 10 chars), probably greeting
            if len(message_lower) < 10:
                return {"intent": "chat", "needs_retrieval": False, "confidence": 0.7}
            
            # Default to chat for uncertain cases
            logger.info("Fallback: Defaulting to chat")
            return {"intent": "chat", "needs_retrieval": False, "confidence": 0.6}
            
        except Exception as e:
            logger.error(f"Intent analysis failed: {e}", exc_info=True)
            # Default to chat (safer than offers)
            return {"intent": "chat", "needs_retrieval": False, "confidence": 0.5}
    
    async def generate_conversation(
        self,
        user_message: str,
        conversation_history: List[Dict[str, str]]
    ) -> str:
        """
        Generate pure conversational response (no offers)
        
        Args:
            user_message: Current user message
            conversation_history: Previous messages
            
        Returns:
            Natural conversational response
        """
        try:
            system_prompt = """You are Orbit, a witty and fun AI assistant for StudentVerse Dubai.

YOUR PERSONALITY:
- Friendly, enthusiastic, genuinely interested in students
- Use emojis, casual language, student slang
- Ask follow-up questions to engage
- Remember conversation context

YOUR ROLE:
You help students discover amazing deals and offers in Dubai. However, right now the user is just chatting with you, not asking for specific offers yet.

GUIDELINES:
1. Respond warmly and naturally to their message
2. Build rapport - ask about them, show interest
3. If appropriate, mention you can help them find deals (but don't push it)
4. Keep responses conversational and brief (2-3 sentences max)
5. Match their energy and tone

Remember: You're having a friendly conversation, not selling anything!"""

            # Build messages
            messages = [{"role": "system", "content": system_prompt}]
            
            # Add history
            if conversation_history:
                messages.extend(conversation_history)
            
            messages.append({"role": "user", "content": user_message})
            
            # Generate response
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.8,  # Higher temperature for creativity
                max_tokens=150
            )
            
            content = response.choices[0].message.content.strip()
            
            logger.info(f"Generated conversation: {content[:50]}...")
            return content
            
        except Exception as e:
            logger.error(f"Conversation generation failed: {e}", exc_info=True)
            return "Hey! 😊 I'm here to help you find awesome student deals. What are you looking for today?"
    
    async def generate_response_with_history(
        self,
        user_message: str,
        offers: List[Dict],
        conversation_history: List[Dict[str, str]]
    ) -> dict:
        """
        Generate response with offers, considering conversation history
        
        Args:
            user_message: Current user message
            offers: Retrieved offers
            conversation_history: Previous messages
            
        Returns:
            Structured response with content and plans
        """
        try:
            # Build enhanced system prompt with context awareness
            system_prompt = self._build_conversational_system_prompt()
            user_prompt = self._build_user_prompt(user_message, offers)
            
            # Build messages with history
            messages = [{"role": "system", "content": system_prompt}]
            
            # Add recent history (last 6 messages for context)
            if conversation_history:
                messages.extend(conversation_history[-6:])
            
            messages.append({"role": "user", "content": user_prompt})
            
            # Call LLM
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=600
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse response
            parsed = self._parse_llm_response(content)
            
            logger.info(f"Generated response with history: {len(parsed.get('plans', []))} plans")
            return parsed
            
        except Exception as e:
            logger.error(f"Response generation with history failed: {e}", exc_info=True)
            return {
                "content": "Oops! Something went wrong. Can you try asking again?",
                "plans": []
            }
    
    def _build_conversational_system_prompt(self) -> str:
        """Build system prompt for contextual conversations"""
        return """You are Orbit, StudentVerse Dubai's witty AI assistant! 🚀

PERSONALITY:
- Fun, enthusiastic, genuinely care about students
- Use emojis, casual language, student slang
- Remember context from the conversation
- Be natural - reference previous messages when relevant

YOUR MISSION:
Help students discover epic deals and offers in Dubai!

CRITICAL RULES:
1. ONLY recommend offers from the Context Data provided
2. NEVER make up or hallucinate offers
3. Select EXACTLY 3 best offers that match the request
4. Reference conversation history naturally when relevant
5. Return ONLY valid JSON

JSON FORMAT:
{
  "content": "Your intro message (mention context if relevant)",
  "plans": [
    {
      "id": "exact-offer-id",
      "title": "exact title",
      "description": "why this is perfect for them",
      "merchant_name": "exact merchant",
      "category": "exact category",
      "discount_value": "exact value"
    }
  ]
}

Keep it fun, contextual, and REAL! 🎉"""

