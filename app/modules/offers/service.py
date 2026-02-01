"""
Offers Service - Phase 2

Business logic for offer filtering, eligibility, and retrieval.
Implements time-based, day-based, and distance-based filtering.
"""

import math
import logging
from datetime import datetime, time as datetime_time, timezone
from typing import List, Optional, Tuple
from app.core.database import get_supabase_client
from app.modules.offers.schemas import (
    OfferListItem, OfferDetail, MerchantBasic, MerchantDetail,
    CategoryResponse, PaginatedOffersResponse
)

logger = logging.getLogger(__name__)


class OfferService:
    """Handles offer operations with eligibility filtering"""
    
    def __init__(self):
        self.supabase = get_supabase_client()
    
    # ================================
    # ELIGIBILITY LOGIC
    # ================================
    
    def is_offer_eligible(
        self,
        offer: dict,
        check_time: bool = True,
        check_day: bool = True
    ) -> bool:
        """
        Check if offer is currently eligible
        
        Rules:
        1. Must be active
        2. Merchant must be active
        3. Must be within date range
        4. Must be within time window (if specified)
        5. Must be valid on current day of week (if specified)
        
        Args:
            offer: Offer dict from database
            check_time: Whether to check time window
            check_day: Whether to check day of week
            
        Returns:
            True if offer is eligible
        """
        now = datetime.now(timezone.utc)
        
        # Rule 1: Offer must be active
        if not offer.get('is_active', False):
            return False
        
        # Rule 2: Check date range validity
        valid_from = offer.get('valid_from')
        valid_until = offer.get('valid_until')
        
        if valid_from and isinstance(valid_from, str):
            valid_from = datetime.fromisoformat(valid_from.replace('Z', '+00:00'))
        if valid_until and isinstance(valid_until, str):
            valid_until = datetime.fromisoformat(valid_until.replace('Z', '+00:00'))
        
        if valid_from and now < valid_from:
            return False
        if valid_until and now > valid_until:
            return False
        
        # Rule 3: Check time window (if specified and check_time=True)
        if check_time:
            time_valid_from = offer.get('time_valid_from')
            time_valid_until = offer.get('time_valid_until')
            
            if time_valid_from and time_valid_until:
                current_time = now.time()
                
                # Convert string times to time objects if needed
                if isinstance(time_valid_from, str):
                    time_valid_from = datetime.strptime(time_valid_from, '%H:%M:%S').time()
                if isinstance(time_valid_until, str):
                    time_valid_until = datetime.strptime(time_valid_until, '%H:%M:%S').time()
                
                # Check if current time is within valid window
                if not (time_valid_from <= current_time <= time_valid_until):
                    return False
        
        # Rule 4: Check day of week (if specified and check_day=True)
        if check_day:
            valid_days = offer.get('valid_days_of_week')
            if valid_days:
                current_day = now.weekday()  # 0=Monday, 6=Sunday
                if current_day not in valid_days:
                    return False
        
        return True
    
    def calculate_distance(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float
    ) -> float:
        """
        Calculate distance between two points using Haversine formula
        
        Args:
            lat1, lon1: First point coordinates
            lat2, lon2: Second point coordinates
            
        Returns:
            Distance in kilometers
        """
        # Earth's radius in kilometers
        R = 6371.0
        
        # Convert to radians
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)
        
        # Haversine formula
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        
        a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        distance = R * c
        return round(distance, 2)
    
    # ================================
    # HOME FEED
    # ================================
    
    async def get_home_feed(
        self,
        user_id: str,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        page: int = 1,
        page_size: int = 20
    ) -> PaginatedOffersResponse:
        """
        Get home feed offers for authenticated user
        
        Filters:
        - Only active offers from active merchants
        - Only offers within valid date range
        - Only offers valid at current time/day
        - Sorted by distance (if location provided) or created_at
        
        Args:
            user_id: Authenticated user ID
            latitude: Optional user latitude
            longitude: Optional user longitude
            page: Page number (1-indexed)
            page_size: Items per page
            
        Returns:
            Paginated offers response
        """
        try:
            # Build query for eligible offers
            query = self.supabase.table("offers").select(
                "*, merchant:merchants(*), category:categories(*)"
            )
            
            # Filter: only active offers
            query = query.eq("is_active", True)
            
            # Filter: only active merchants
            query = query.eq("merchants.is_active", True)
            
            # Filter: date range validity
            now = datetime.now(timezone.utc).isoformat()
            query = query.lte("valid_from", now).gte("valid_until", now)
            
            # Execute query
            result = query.execute()
            
            if not result.data:
                return PaginatedOffersResponse(
                    items=[],
                    total=0,
                    page=page,
                    page_size=page_size,
                    total_pages=0
                )
            
            # Filter offers by time and day eligibility
            eligible_offers = [
                offer for offer in result.data
                if self.is_offer_eligible(offer, check_time=True, check_day=True)
            ]
            
            # Calculate distance if location provided
            if latitude is not None and longitude is not None:
                for offer in eligible_offers:
                    merchant = offer.get('merchant')
                    if merchant and merchant.get('latitude') and merchant.get('longitude'):
                        distance = self.calculate_distance(
                            latitude, longitude,
                            merchant['latitude'], merchant['longitude']
                        )
                        offer['distance_km'] = distance
                    else:
                        offer['distance_km'] = None
                
                # Sort by distance (nulls last), then by created_at
                eligible_offers.sort(
                    key=lambda x: (x['distance_km'] is None, x['distance_km'], x['created_at']),
                    reverse=False
                )
            else:
                # Sort by created_at (newest first)
                eligible_offers.sort(key=lambda x: x['created_at'], reverse=True)
            
            # Pagination
            total = len(eligible_offers)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            paginated_offers = eligible_offers[start_idx:end_idx]
            
            # Convert to response models
            offer_items = [
                self._convert_to_list_item(offer)
                for offer in paginated_offers
            ]
            
            total_pages = math.ceil(total / page_size) if total > 0 else 0
            
            return PaginatedOffersResponse(
                items=offer_items,
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages
            )
            
        except Exception as e:
            logger.error(f"Error fetching home feed: {e}")
            raise
    
    # ================================
    # SEARCH
    # ================================
    
    async def search_offers(
        self,
        user_id: str,
        query: Optional[str] = None,
        category_id: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius_km: Optional[float] = None,
        page: int = 1,
        page_size: int = 20
    ) -> PaginatedOffersResponse:
        """
        Search offers with filters
        
        Args:
            user_id: Authenticated user ID
            query: Search query (title + description)
            category_id: Filter by category
            latitude: User latitude for distance filtering
            longitude: User longitude for distance filtering
            radius_km: Maximum distance in km
            page: Page number
            page_size: Items per page
            
        Returns:
            Paginated search results
        """
        try:
            # Build base query
            db_query = self.supabase.table("offers").select(
                "*, merchant:merchants(*), category:categories(*)"
            )
            
            # Filter: only active offers from active merchants
            db_query = db_query.eq("is_active", True)
            db_query = db_query.eq("merchants.is_active", True)
            
            # Filter: date range
            now = datetime.now(timezone.utc).isoformat()
            db_query = db_query.lte("valid_from", now).gte("valid_until", now)
            
            # Filter: category
            if category_id:
                db_query = db_query.eq("category_id", category_id)
            
            # Filter: text search (if query provided)
            if query:
                # Supabase text search - search in title and description
                db_query = db_query.or_(f"title.ilike.%{query}%,description.ilike.%{query}%")
            
            # Execute query
            result = db_query.execute()
            
            if not result.data:
                return PaginatedOffersResponse(
                    items=[],
                    total=0,
                    page=page,
                    page_size=page_size,
                    total_pages=0
                )
            
            # Filter by time/day eligibility
            eligible_offers = [
                offer for offer in result.data
                if self.is_offer_eligible(offer, check_time=True, check_day=True)
            ]
            
            # Distance filtering and calculation
            if latitude is not None and longitude is not None:
                offers_with_distance = []
                
                for offer in eligible_offers:
                    merchant = offer.get('merchant')
                    if merchant and merchant.get('latitude') and merchant.get('longitude'):
                        distance = self.calculate_distance(
                            latitude, longitude,
                            merchant['latitude'], merchant['longitude']
                        )
                        
                        # Filter by radius if specified
                        if radius_km is None or distance <= radius_km:
                            offer['distance_km'] = distance
                            offers_with_distance.append(offer)
                    elif radius_km is None:
                        # Include offers without location if no radius filter
                        offer['distance_km'] = None
                        offers_with_distance.append(offer)
                
                eligible_offers = offers_with_distance
                # Sort by distance
                eligible_offers.sort(
                    key=lambda x: (x['distance_km'] is None, x['distance_km']),
                    reverse=False
                )
            else:
                # Sort by relevance (created_at for now)
                eligible_offers.sort(key=lambda x: x['created_at'], reverse=True)
            
            # Pagination
            total = len(eligible_offers)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            paginated_offers = eligible_offers[start_idx:end_idx]
            
            # Convert to response models
            offer_items = [
                self._convert_to_list_item(offer)
                for offer in paginated_offers
            ]
            
            total_pages = math.ceil(total / page_size) if total > 0 else 0
            
            return PaginatedOffersResponse(
                items=offer_items,
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages
            )
            
        except Exception as e:
            logger.error(f"Error searching offers: {e}")
            raise
    
    # ================================
    # NEARBY OFFERS
    # ================================
    
    async def get_nearby_offers(
        self,
        user_id: str,
        latitude: float,
        longitude: float,
        radius_km: float = 5.0,
        category_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> PaginatedOffersResponse:
        """
        Get offers near user location
        
        Args:
            user_id: Authenticated user ID
            latitude: User latitude
            longitude: User longitude
            radius_km: Search radius in km (max 50km enforced)
            category_id: Optional category filter
            page: Page number
            page_size: Items per page
            
        Returns:
            Paginated nearby offers
        """
        # Enforce max radius
        radius_km = min(radius_km, 50.0)
        
        return await self.search_offers(
            user_id=user_id,
            query=None,
            category_id=category_id,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            page=page,
            page_size=page_size
        )
    
    # ================================
    # OFFER DETAIL
    # ================================
    
    async def get_offer_detail(
        self,
        user_id: str,
        offer_id: str,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None
    ) -> OfferDetail:
        """
        Get detailed offer information
        
        Args:
            user_id: Authenticated user ID
            offer_id: Offer ID
            latitude: Optional user latitude for distance
            longitude: Optional user longitude for distance
            
        Returns:
            Detailed offer information
            
        Raises:
            ValueError: If offer not found or not eligible
        """
        try:
            # Fetch offer with merchant and category
            result = self.supabase.table("offers").select(
                "*, merchant:merchants(*), category:categories(*)"
            ).eq("id", offer_id).execute()
            
            if not result.data:
                raise ValueError("Offer not found")
            
            offer = result.data[0]
            
            # Check if offer is eligible
            if not self.is_offer_eligible(offer, check_time=True, check_day=True):
                raise ValueError("Offer is not currently available")
            
            # Check if merchant is active
            merchant = offer.get('merchant')
            if not merchant or not merchant.get('is_active'):
                raise ValueError("Offer is not currently available")
            
            # Calculate distance if location provided
            if latitude is not None and longitude is not None:
                if merchant.get('latitude') and merchant.get('longitude'):
                    distance = self.calculate_distance(
                        latitude, longitude,
                        merchant['latitude'], merchant['longitude']
                    )
                    offer['distance_km'] = distance
            
            # Convert to detail model
            return self._convert_to_detail(offer)
            
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error fetching offer detail: {e}")
            raise
    
    # ================================
    # CATEGORIES
    # ================================
    
    async def get_categories(self) -> List[CategoryResponse]:
        """
        Get all active categories
        
        Returns:
            List of active categories sorted by sort_order
        """
        try:
            result = self.supabase.table("categories").select("*").eq(
                "is_active", True
            ).order("sort_order").execute()
            
            return [CategoryResponse(**cat) for cat in result.data]
            
        except Exception as e:
            logger.error(f"Error fetching categories: {e}")
            raise
    
    # ================================
    # HELPER METHODS
    # ================================
    
    def _convert_to_list_item(self, offer: dict) -> OfferListItem:
        """Convert offer dict to OfferListItem"""
        merchant_data = offer.get('merchant', {})
        category_data = offer.get('category')
        
        return OfferListItem(
            id=offer['id'],
            title=offer['title'],
            description=offer['description'],
            merchant=MerchantBasic(**merchant_data) if merchant_data else None,
            category=CategoryResponse(**category_data) if category_data else None,
            offer_type=offer['offer_type'],
            discount_value=offer.get('discount_value'),
            original_price=offer.get('original_price'),
            discounted_price=offer.get('discounted_price'),
            image_url=offer.get('image_url'),
            valid_from=offer['valid_from'],
            valid_until=offer['valid_until'],
            distance_km=offer.get('distance_km'),
            is_featured=offer.get('is_featured', False),
            created_at=offer['created_at']
        )
    
    def _convert_to_detail(self, offer: dict) -> OfferDetail:
        """Convert offer dict to OfferDetail"""
        merchant_data = offer.get('merchant', {})
        category_data = offer.get('category')
        
        return OfferDetail(
            id=offer['id'],
            title=offer['title'],
            description=offer['description'],
            terms_conditions=offer.get('terms_conditions'),
            merchant=MerchantDetail(**merchant_data) if merchant_data else None,
            category=CategoryResponse(**category_data) if category_data else None,
            offer_type=offer['offer_type'],
            discount_value=offer.get('discount_value'),
            original_price=offer.get('original_price'),
            discounted_price=offer.get('discounted_price'),
            image_url=offer.get('image_url'),
            images=offer.get('images'),
            valid_from=offer['valid_from'],
            valid_until=offer['valid_until'],
            time_valid_from=offer.get('time_valid_from'),
            time_valid_until=offer.get('time_valid_until'),
            valid_days_of_week=offer.get('valid_days_of_week'),
            max_claims_per_user=offer.get('max_claims_per_user'),
            total_claims=offer.get('total_claims', 0),
            max_total_claims=offer.get('max_total_claims'),
            is_featured=offer.get('is_featured', False),
            distance_km=offer.get('distance_km'),
            created_at=offer['created_at'],
            updated_at=offer.get('updated_at')
        )
