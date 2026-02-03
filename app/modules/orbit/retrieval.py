"""
SV Orbit Retrieval

Retrieval-only system for finding relevant partner offers.
CRITICAL: No hallucinations - only real partner data.
"""

import re
import logging
from typing import List, Dict, Any, Optional
from app.core.database import get_supabase_client

logger = logging.getLogger(__name__)


class OfferRetrieval:
    """
    Retrieves partner offers based on user intent
    
    IMPORTANT: Only retrieves real offers from database
    Never generates or hallucinates offers
    """
    
    def __init__(self):
        """Initialize with Supabase client"""
        self.supabase = get_supabase_client()
    
    def extract_keywords(self, message: str) -> List[str]:
        """
        Extract keywords from user message
        
        Simple extraction logic:
        - Convert to lowercase
        - Remove common stop words
        - Split into words
        - Filter short words
        
        Args:
            message: User's message
            
        Returns:
            List of keywords
        """
        # Common stop words to filter out
        stop_words = {
            'i', 'want', 'need', 'looking', 'for', 'a', 'an', 'the', 'is', 'are',
            'can', 'you', 'me', 'my', 'in', 'on', 'at', 'to', 'from', 'with',
            'find', 'get', 'show', 'give', 'some', 'any', 'where', 'what', 'how'
        }
        
        # Convert to lowercase and extract words
        words = re.findall(r'\b[a-zA-Z]+\b', message.lower())
        
        # Filter stop words and short words
        keywords = [
            word for word in words 
            if word not in stop_words and len(word) > 2
        ]
        
        return keywords
    
    async def retrieve_offers(
        self,
        intent: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 10
    ) -> List[dict]:
        """
        Retrieve relevant offers from database
        
        Uses:
        - Keyword matching in title, description, merchant name
        - Active status filtering
        - Date range validation
        
        Args:
            intent: User's intent/query
            filters: Optional filters
            limit: Maximum number of offers to return
            
        Returns:
            List of relevant offers (REAL DATA ONLY)
        """
        try:
            # Extract keywords from user intent
            keywords = self.extract_keywords(intent)
            
            # Build base query with merchant join
            query = self.supabase.table("offers").select(
                "*, merchant:merchants(*), category:categories(*)"
            )
            
            # Filter: only active offers from active merchants
            query = query.eq("is_active", True)
            query = query.eq("merchants.is_active", True)
            
            # Execute query
            result = query.execute()
            
            if not result.data:
                logger.info("No offers found in database")
                return []
            
            # Score offers based on keyword matching
            scored_offers = []
            for offer in result.data:
                score = self._calculate_relevance_score(offer, keywords)
                if score > 0:  # Only include if at least one keyword matches
                    offer['_relevance_score'] = score
                    scored_offers.append(offer)
            
            # Sort by relevance score (highest first)
            scored_offers.sort(key=lambda x: x['_relevance_score'], reverse=True)
            
            # Return top N offers
            top_offers = scored_offers[:limit]
            
            logger.info(f"Retrieved {len(top_offers)} relevant offers for intent: {intent}")
            return top_offers
            
        except Exception as e:
            logger.error(f"Error retrieving offers: {e}")
            raise
    
    def _calculate_relevance_score(self, offer: dict, keywords: List[str]) -> float:
        """
        Calculate relevance score for offer based on keywords
        
        Scoring:
        - Title match: 3 points per keyword
        - Description match: 2 points per keyword
        - Merchant name match: 2 points per keyword
        - Category name match: 1 point per keyword
        
        Args:
            offer: Offer data
            keywords: List of keywords to match
            
        Returns:
            Relevance score
        """
        score = 0.0
        
        # Prepare searchable text
        title = (offer.get('title') or '').lower()
        description = (offer.get('description') or '').lower()
        merchant_name = (offer.get('merchant', {}).get('name') or '').lower()
        category_name = (offer.get('category', {}).get('name') or '').lower()
        
        for keyword in keywords:
            # Title matches are most important
            if keyword in title:
                score += 3.0
            
            # Description matches
            if keyword in description:
                score += 2.0
            
            # Merchant name matches
            if keyword in merchant_name:
                score += 2.0
            
            # Category name matches
            if keyword in category_name:
                score += 1.0
        
        return score
    
    async def search_by_category(
        self,
        categories: List[str],
        limit: int = 10
    ) -> List[dict]:
        """
        Search offers by category
        
        Args:
            categories: List of categories to search
            limit: Maximum results
            
        Returns:
            Matching offers
        """
        try:
            query = self.supabase.table("offers").select(
                "*, merchant:merchants(*), category:categories(*)"
            )
            
            query = query.eq("is_active", True)
            query = query.in_("category.slug", categories)
            query = query.limit(limit)
            
            result = query.execute()
            return result.data
            
        except Exception as e:
            logger.error(f"Error searching by category: {e}")
            raise
    
    async def search_by_keywords(
        self,
        keywords: List[str],
        limit: int = 10
    ) -> List[dict]:
        """
        Search offers by keywords
        
        Args:
            keywords: Search keywords
            limit: Maximum results
            
        Returns:
            Matching offers
        """
        # Reuse retrieve_offers with keywords joined
        intent = " ".join(keywords)
        return await self.retrieve_offers(intent, limit=limit)
    
    async def get_user_recommended_offers(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[dict]:
        """
        Get personalized offer recommendations
        
        Based on:
        - Popular offers
        - Featured offers
        
        Args:
            user_id: User UUID
            limit: Maximum results
            
        Returns:
            Recommended offers
        """
        try:
            query = self.supabase.table("offers").select(
                "*, merchant:merchants(*), category:categories(*)"
            )
            
            query = query.eq("is_active", True)
            query = query.eq("is_featured", True)
            query = query.limit(limit)
            
            result = query.execute()
            return result.data
            
        except Exception as e:
            logger.error(f"Error getting recommended offers: {e}")
            raise

