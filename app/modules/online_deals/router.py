"""
Online Deals Router

API endpoints for online deals (discount codes and affiliate links).
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer

from app.core.security import get_current_user
from app.modules.online_deals.service import OnlineDealService
from app.modules.online_deals.schemas import (
    PaginatedOnlineDealsResponse,
    OnlineDealDetail,
    OnlineDealListItem,
    OnlineDealCreateRequest,
    OnlineDealUpdateRequest,
    MerchantBasic
)

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter()

# Security
security = HTTPBearer()


# ================================
# DEPENDENCY INJECTION
# ================================

def get_online_deal_service() -> OnlineDealService:
    """Dependency for online deal service"""
    return OnlineDealService()


# ================================
# PUBLIC ENDPOINTS (Authenticated Users)
# ================================

@router.get(
    "",
    response_model=PaginatedOnlineDealsResponse,
    summary="Get online deals",
    description="Returns paginated list of active online deals (discount codes and affiliate links)."
)
async def get_online_deals(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    category: Optional[str] = Query(None, description="Filter by category"),
    current_user: dict = Depends(get_current_user),
    deal_service: OnlineDealService = Depends(get_online_deal_service)
):
    """
    Get online deals list.
    
    Security:
    - Requires JWT authentication
    
    Args:
        page: Page number (default: 1)
        page_size: Items per page (default: 20, max: 100)
        category: Optional category filter
        current_user: Authenticated user from JWT
        deal_service: Injected deal service
        
    Returns:
        Paginated list of online deals
    """
    try:
        result = await deal_service.get_online_deals(
            page=page,
            page_size=page_size,
            category=category
        )
        
        # Transform data to include merchant and isOnline flag
        items = [
            OnlineDealListItem(
                id=item['id'],
                type=item['type'],
                merchant=MerchantBasic(
                    id=item['merchants']['id'],
                    name=item['merchants']['name'],
                    logo_url=item['merchants'].get('logo_url'),
                    color=item['merchants'].get('color')
                ),
                category=item['category'],
                title=item['title'],
                discount=item['discount'],
                description=item.get('description'),
                image=item['merchants'].get('logo_url') or item['image'],
                brand_color=item['merchants'].get('color') or item.get('brand_color'),
                highlights=item.get('highlights'),
                isOnline=True,
                is_active=item['is_active'],
                created_at=item['created_at']
            )
            for item in result['items']
        ]
        
        return PaginatedOnlineDealsResponse(
            items=items,
            total=result['total'],
            page=result['page'],
            page_size=result['page_size'],
            total_pages=result['total_pages']
        )
        
    except Exception as e:
        logger.error(f"Error in get_online_deals: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch online deals"
        )


@router.get(
    "/{deal_id}",
    response_model=OnlineDealDetail,
    summary="Get online deal details",
    description="Returns full details for a single online deal by ID."
)
async def get_online_deal_by_id(
    deal_id: str,
    current_user: dict = Depends(get_current_user),
    deal_service: OnlineDealService = Depends(get_online_deal_service)
):
    """
    Get online deal by ID.
    
    Security:
    - Requires JWT authentication
    
    Args:
        deal_id: UUID of the online deal
        current_user: Authenticated user from JWT
        deal_service: Injected deal service
        
    Returns:
        Full online deal details
        
    Raises:
        404: If deal not found
    """
    try:
        result = await deal_service.get_online_deal_by_id(deal_id)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Online deal not found"
            )
        
        return OnlineDealDetail(
            id=result['id'],
            type=result['type'],
            merchant=MerchantBasic(
                id=result['merchants']['id'],
                name=result['merchants']['name'],
                logo_url=result['merchants'].get('logo_url'),
                color=result['merchants'].get('color')
            ),
            category=result['category'],
            title=result['title'],
            discount=result['discount'],
            description=result.get('description'),
            image=result['merchants'].get('logo_url') or result['image'],
            brand_color=result['merchants'].get('color') or result.get('brand_color'),
            highlights=result.get('highlights'),
            terms=result.get('terms'),
            discount_code=result.get('discount_code'),
            redemption_url=result['redemption_url'],
            isOnline=True,
            is_active=result['is_active'],
            created_at=result['created_at'],
            updated_at=result.get('updated_at')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_online_deal_by_id: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch online deal"
        )


# ================================
# ADMIN ENDPOINTS
# ================================

@router.post(
    "",
    response_model=OnlineDealDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create online deal (Admin)",
    description="Creates a new online deal. Admin access required."
)
async def create_online_deal(
    deal_request: OnlineDealCreateRequest,
    current_user: dict = Depends(get_current_user),
    deal_service: OnlineDealService = Depends(get_online_deal_service)
):
    """
    Create a new online deal (Admin only).
    
    Security:
    - Requires JWT authentication
    - Requires admin role (to be implemented)
    
    Args:
        deal_request: Online deal creation request
        current_user: Authenticated user from JWT
        deal_service: Injected deal service
        
    Returns:
        Created online deal
        
    Raises:
        400: If validation fails
        403: If not admin
    """
    # TODO: Add admin role check
    
    try:
        result = await deal_service.create_online_deal(
            deal_data=deal_request.model_dump(exclude_unset=True)
        )
        
        return OnlineDealDetail(
            id=result['id'],
            type=result['type'],
            merchant=MerchantBasic(
                id=result['merchants']['id'],
                name=result['merchants']['name'],
                logo_url=result['merchants'].get('logo_url')
            ),
            category=result['category'],
            title=result['title'],
            discount=result['discount'],
            description=result.get('description'),
            image=result['image'],
            brand_color=result.get('brand_color'),
            highlights=result.get('highlights'),
            terms=result.get('terms'),
            discount_code=result.get('discount_code'),
            redemption_url=result['redemption_url'],
            isOnline=True,
            is_active=result['is_active'],
            created_at=result['created_at'],
            updated_at=result.get('updated_at')
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error in create_online_deal: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create online deal"
        )


@router.put(
    "/{deal_id}",
    response_model=OnlineDealDetail,
    summary="Update online deal (Admin)",
    description="Updates an existing online deal. Admin access required."
)
async def update_online_deal(
    deal_id: str,
    deal_request: OnlineDealUpdateRequest,
    current_user: dict = Depends(get_current_user),
    deal_service: OnlineDealService = Depends(get_online_deal_service)
):
    """
    Update an existing online deal (Admin only).
    
    Security:
    - Requires JWT authentication
    - Requires admin role (to be implemented)
    
    Args:
        deal_id: UUID of the online deal
        deal_request: Online deal update request
        current_user: Authenticated user from JWT
        deal_service: Injected deal service
        
    Returns:
        Updated online deal
        
    Raises:
        404: If deal not found
        403: If not admin
    """
    # TODO: Add admin role check
    
    try:
        result = await deal_service.update_online_deal(
            deal_id=deal_id,
            deal_data=deal_request.model_dump(exclude_unset=True)
        )
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Online deal not found"
            )
        
        return OnlineDealDetail(
            id=result['id'],
            type=result['type'],
            merchant=MerchantBasic(
                id=result['merchants']['id'],
                name=result['merchants']['name'],
                logo_url=result['merchants'].get('logo_url')
            ),
            category=result['category'],
            title=result['title'],
            discount=result['discount'],
            description=result.get('description'),
            image=result['image'],
            brand_color=result.get('brand_color'),
            highlights=result.get('highlights'),
            terms=result.get('terms'),
            discount_code=result.get('discount_code'),
            redemption_url=result['redemption_url'],
            isOnline=True,
            is_active=result['is_active'],
            created_at=result['created_at'],
            updated_at=result.get('updated_at')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in update_online_deal: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update online deal"
        )


@router.delete(
    "/{deal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete online deal (Admin)",
    description="Soft deletes an online deal. Admin access required."
)
async def delete_online_deal(
    deal_id: str,
    current_user: dict = Depends(get_current_user),
    deal_service: OnlineDealService = Depends(get_online_deal_service)
):
    """
    Delete an online deal (Admin only).
    
    Security:
    - Requires JWT authentication
    - Requires admin role (to be implemented)
    
    Args:
        deal_id: UUID of the online deal
        current_user: Authenticated user from JWT
        deal_service: Injected deal service
        
    Raises:
        404: If deal not found
        403: If not admin
    """
    # TODO: Add admin role check
    
    try:
        success = await deal_service.delete_online_deal(deal_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Online deal not found"
            )
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in delete_online_deal: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete online deal"
        )
