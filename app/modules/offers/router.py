"""
Offers Router - Phase 2

API endpoints for offers, home feed, search, and nearby offers.
All endpoints require JWT authentication.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer

from app.core.security import get_current_user
from app.modules.offers.service import OfferService
from app.modules.offers.schemas import (
    PaginatedOffersResponse,
    OfferDetail,
    CategoriesResponse,
    HomeFeedRequest,
    SearchRequest,
    NearbyOffersRequest
)

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter()

# Security
security = HTTPBearer()


# ================================
# DEPENDENCY INJECTION
# ================================

def get_offer_service() -> OfferService:
    """Dependency for offer service"""
    return OfferService()


# ================================
# HOME FEED ENDPOINT
# ================================

@router.get(
    "/home",
    response_model=PaginatedOffersResponse,
    summary="Get home feed offers",
    description="Returns personalized offer feed for authenticated user. Sorted by distance if location provided."
)
async def get_home_feed(
    latitude: Optional[float] = Query(None, ge=-90, le=90, description="User latitude"),
    longitude: Optional[float] = Query(None, ge=-180, le=180, description="User longitude"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: dict = Depends(get_current_user),
    offer_service: OfferService = Depends(get_offer_service)
):
    """
    Get home feed offers
    
    Security:
    - Requires JWT authentication
    - Rate limited to 100 requests/minute
    - User ID derived from JWT (never from request)
    
    Filters applied:
    - Only active offers from active merchants
    - Only offers within valid date range
    - Only offers valid at current time/day
    - Sorted by distance (if location provided) or created_at
    
    Args:
        latitude: Optional user latitude for distance sorting
        longitude: Optional user longitude for distance sorting
        page: Page number (default: 1)
        page_size: Items per page (default: 20, max: 100)
        current_user: Authenticated user from JWT
        offer_service: Injected offer service
        
    Returns:
        Paginated list of eligible offers
    """
    try:
        # Validate location parameters
        if (latitude is None) != (longitude is None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Both latitude and longitude must be provided together"
            )
        
        # Get user ID from JWT (NEVER from request)
        user_id = current_user['id']
        
        # Fetch home feed
        result = await offer_service.get_home_feed(
            user_id=user_id,
            latitude=latitude,
            longitude=longitude,
            page=page,
            page_size=page_size
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_home_feed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch home feed"
        )


# ================================
# SEARCH ENDPOINT
# ================================

@router.get(
    "/search",
    response_model=PaginatedOffersResponse,
    summary="Search offers",
    description="Search offers by keyword, category, and location with radius filtering"
)
async def search_offers(
    query: Optional[str] = Query(None, max_length=200, description="Search query"),
    category_id: Optional[str] = Query(None, description="Filter by category ID"),
    latitude: Optional[float] = Query(None, ge=-90, le=90, description="User latitude"),
    longitude: Optional[float] = Query(None, ge=-180, le=180, description="User longitude"),
    radius_km: Optional[float] = Query(None, ge=0, le=50, description="Search radius in km (max 50)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: dict = Depends(get_current_user),
    offer_service: OfferService = Depends(get_offer_service)
):
    """
    Search offers with filters
    
    Security:
    - Requires JWT authentication
    - Rate limited to 60 requests/minute
    - Search query sanitized to prevent injection
    - User ID derived from JWT
    
    Filters:
    - Keyword search in title and description
    - Category filtering
    - Distance-based filtering with radius
    - Only active and eligible offers
    
    Args:
        query: Search keyword (sanitized)
        category_id: Filter by category
        latitude: User latitude for distance filtering
        longitude: User longitude for distance filtering
        radius_km: Maximum distance in km (max 50km)
        page: Page number
        page_size: Items per page
        current_user: Authenticated user from JWT
        offer_service: Injected offer service
        
    Returns:
        Paginated search results
    """
    try:
        # Validate location and radius
        if radius_km is not None:
            if latitude is None or longitude is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Latitude and longitude required for radius filtering"
                )
        
        # Validate location pair
        if (latitude is None) != (longitude is None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Both latitude and longitude must be provided together"
            )
        
        # Sanitize query (basic validation - Pydantic does more)
        if query:
            query = query.strip()
            if len(query) < 2:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Search query must be at least 2 characters"
                )
        
        # Get user ID from JWT
        user_id = current_user['id']
        
        # Perform search
        result = await offer_service.search_offers(
            user_id=user_id,
            query=query,
            category_id=category_id,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            page=page,
            page_size=page_size
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in search_offers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search offers"
        )


# ================================
# NEARBY OFFERS ENDPOINT
# ================================

@router.get(
    "/nearby",
    response_model=PaginatedOffersResponse,
    summary="Get nearby offers",
    description="Get offers near user location sorted by distance"
)
async def get_nearby_offers(
    latitude: float = Query(..., ge=-90, le=90, description="User latitude (required)"),
    longitude: float = Query(..., ge=-180, le=180, description="User longitude (required)"),
    radius_km: float = Query(5.0, ge=0.1, le=50, description="Search radius in km (default: 5, max: 50)"),
    category_id: Optional[str] = Query(None, description="Filter by category ID"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: dict = Depends(get_current_user),
    offer_service: OfferService = Depends(get_offer_service)
):
    """
    Get nearby offers
    
    Security:
    - Requires JWT authentication
    - Rate limited to 100 requests/minute
    - Max radius enforced server-side (50km)
    - User ID derived from JWT
    
    Returns offers sorted by distance from user location.
    
    Args:
        latitude: User latitude (required)
        longitude: User longitude (required)
        radius_km: Search radius in km (default: 5, max: 50)
        category_id: Optional category filter
        page: Page number
        page_size: Items per page
        current_user: Authenticated user from JWT
        offer_service: Injected offer service
        
    Returns:
        Paginated nearby offers sorted by distance
    """
    try:
        # Get user ID from JWT
        user_id = current_user['id']
        
        # Fetch nearby offers
        result = await offer_service.get_nearby_offers(
            user_id=user_id,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            category_id=category_id,
            page=page,
            page_size=page_size
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_nearby_offers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch nearby offers"
        )


# ================================
# OFFER DETAIL ENDPOINT
# ================================

@router.get(
    "/{offer_id}",
    response_model=OfferDetail,
    summary="Get offer details",
    description="Get detailed information about a specific offer"
)
async def get_offer_detail(
    offer_id: str,
    latitude: Optional[float] = Query(None, ge=-90, le=90, description="User latitude for distance"),
    longitude: Optional[float] = Query(None, ge=-180, le=180, description="User longitude for distance"),
    current_user: dict = Depends(get_current_user),
    offer_service: OfferService = Depends(get_offer_service)
):
    """
    Get offer details
    
    Security:
    - Requires JWT authentication
    - Rate limited to 100 requests/minute
    - Validates offer is active and eligible
    - Hides internal sensitive fields
    - User ID derived from JWT
    
    Args:
        offer_id: Offer ID
        latitude: Optional user latitude for distance calculation
        longitude: Optional user longitude for distance calculation
        current_user: Authenticated user from JWT
        offer_service: Injected offer service
        
    Returns:
        Detailed offer information
        
    Raises:
        404: Offer not found or not eligible
    """
    try:
        # Validate location pair
        if (latitude is None) != (longitude is None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Both latitude and longitude must be provided together"
            )
        
        # Get user ID from JWT
        user_id = current_user['id']
        
        # Fetch offer detail
        offer = await offer_service.get_offer_detail(
            user_id=user_id,
            offer_id=offer_id,
            latitude=latitude,
            longitude=longitude
        )
        
        return offer
        
    except ValueError as e:
        # Offer not found or not eligible
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_offer_detail: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch offer details"
        )


# ================================
# CATEGORIES ENDPOINT
# ================================

@router.get(
    "/categories/list",
    response_model=CategoriesResponse,
    summary="Get all categories",
    description="Get list of all active offer categories"
)
async def get_categories(
    current_user: dict = Depends(get_current_user),
    offer_service: OfferService = Depends(get_offer_service)
):
    """
    Get all active categories
    
    Security:
    - Requires JWT authentication
    - Rate limited to 100 requests/minute
    
    Returns:
        List of active categories sorted by sort_order
    """
    try:
        categories = await offer_service.get_categories()
        return CategoriesResponse(categories=categories)
        
    except Exception as e:
        logger.error(f"Error in get_categories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch categories"
        )
