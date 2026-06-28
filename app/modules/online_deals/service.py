"""
Online Deals Service

Business logic for online deals.
"""

import math
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.core.database import get_supabase_client

logger = logging.getLogger(__name__)


class OnlineDealService:
    """Service for online deals operations"""
    
    def __init__(self):
        self.supabase = get_supabase_client()
    
    async def get_online_deals(
        self,
        page: int = 1,
        page_size: int = 20,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get paginated list of online deals with merchant info.
        
        Args:
            page: Page number (1-indexed)
            page_size: Number of items per page
            category: Optional category filter
            
        Returns:
            Dictionary with paginated online deals including merchant data
        """
        try:
            # Build query with merchant join
            # Note: Supabase doesn't support proper joins in the Python client
            # So we fetch online deals first, then fetch merchants separately
            query = (
                self.supabase.table('online_deals')
                .select('*, merchants!inner(*)', count='exact')
                .eq('is_active', True)
                .order('is_featured', desc=True)
                .order('created_at', desc=True)
            )
            
            # Apply category filter
            if category:
                query = query.ilike('category', f'%{category}%')
            
            # Calculate pagination
            from_offset = (page - 1) * page_size
            query = query.range(from_offset, from_offset + page_size - 1)
            
            # Execute query
            response = query.execute()
            
            items = response.data
            total = response.count or 0
            total_pages = math.ceil(total / page_size) if total > 0 else 0
            
            return {
                'items': items,
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': total_pages
            }
            
        except Exception as e:
            logger.error(f"Error in get_online_deals: {e}")
            raise
    
    async def get_online_deal_by_id(self, deal_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single online deal by ID.
        
        Args:
            deal_id: UUID of the online deal
            
        Returns:
            Online deal data or None if not found
        """
        try:
            response = (
                self.supabase.table('online_deals')
                .select('*, merchants(*)')
                .eq('id', deal_id)
                .eq('is_active', True)
                .execute()
            )
            
            if not response.data:
                return None
            
            return response.data[0]
            
        except Exception as e:
            logger.error(f"Error in get_online_deal_by_id: {e}")
            raise
    
    async def create_online_deal(
        self,
        deal_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a new online deal (Admin only).
        
        Args:
            deal_data: Online deal data from request
            
        Returns:
            Created online deal
        """
        try:
            # Validate discount_code for discount_code type
            if deal_data.get('type') == 'discount_code' and not deal_data.get('discount_code'):
                raise ValueError("discount_code is required for discount_code type deals")
            
            if deal_data.get('type') == 'affiliate_link':
                # Clear discount_code for affiliate links
                deal_data['discount_code'] = None
            
            insert_response = (
                self.supabase.table('online_deals')
                .insert(deal_data)
                .execute()
            )
            
            created_id = insert_response.data[0]['id']
            
            # Fetch with merchant data
            response = (
                self.supabase.table('online_deals')
                .select('*, merchants(*)')
                .eq('id', created_id)
                .execute()
            )
            
            return response.data[0]
            
        except Exception as e:
            logger.error(f"Error in create_online_deal: {e}")
            raise
    
    async def update_online_deal(
        self,
        deal_id: str,
        deal_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update an existing online deal (Admin only).
        
        Args:
            deal_id: UUID of the online deal
            deal_data: Updated deal data
            
        Returns:
            Updated online deal or None if not found
        """
        try:
            # Add updated_at timestamp
            deal_data['updated_at'] = datetime.utcnow().isoformat()
            
            update_response = (
                self.supabase.table('online_deals')
                .update(deal_data)
                .eq('id', deal_id)
                .execute()
            )
            
            if not update_response.data:
                return None
            
            # Fetch with merchant data
            response = (
                self.supabase.table('online_deals')
                .select('*, merchants(*)')
                .eq('id', deal_id)
                .execute()
            )
            
            return response.data[0] if response.data else None
            
        except Exception as e:
            logger.error(f"Error in update_online_deal: {e}")
            raise
    
    async def delete_online_deal(self, deal_id: str) -> bool:
        """
        Soft delete an online deal by setting is_active=False (Admin only).
        
        Args:
            deal_id: UUID of the online deal
            
        Returns:
            True if successful
        """
        try:
            response = (
                self.supabase.table('online_deals')
                .update({
                    'is_active': False,
                    'updated_at': datetime.utcnow().isoformat()
                })
                .eq('id', deal_id)
                .execute()
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error in delete_online_deal: {e}")
            raise
