"""
Online Deals Service

Business logic for online deals.
"""

import math
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.core.database import fetch_one, fetch_all, execute, fetch_val

logger = logging.getLogger(__name__)


class OnlineDealService:
    """Service for online deals operations"""

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
            from_offset = (page - 1) * page_size
            if category:
                sql = """
                    SELECT od.*, row_to_json(m.*) as merchants
                    FROM online_deals od
                    INNER JOIN merchants m ON m.id = od.merchant_id
                    WHERE od.is_active = true AND od.category ILIKE %s
                    ORDER BY od.is_featured DESC, od.created_at DESC
                    LIMIT %s OFFSET %s
                """
                count_sql = "SELECT COUNT(*) FROM online_deals WHERE is_active = true AND category ILIKE %s"
                items = fetch_all(sql, (f"%{category}%", page_size, from_offset))
                total = fetch_val(count_sql, (f"%{category}%",)) or 0
            else:
                sql = """
                    SELECT od.*, row_to_json(m.*) as merchants
                    FROM online_deals od
                    INNER JOIN merchants m ON m.id = od.merchant_id
                    WHERE od.is_active = true
                    ORDER BY od.is_featured DESC, od.created_at DESC
                    LIMIT %s OFFSET %s
                """
                count_sql = "SELECT COUNT(*) FROM online_deals WHERE is_active = true"
                items = fetch_all(sql, (page_size, from_offset))
                total = fetch_val(count_sql) or 0

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
            sql = """
                SELECT od.*, row_to_json(m.*) as merchants
                FROM online_deals od
                LEFT JOIN merchants m ON m.id = od.merchant_id
                WHERE od.id = %s AND od.is_active = true
            """
            return fetch_one(sql, (deal_id,))

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
            if deal_data.get('type') == 'discount_code' and not deal_data.get('discount_code'):
                raise ValueError("discount_code is required for discount_code type deals")

            if deal_data.get('type') == 'affiliate_link':
                deal_data['discount_code'] = None

            keys = list(deal_data.keys())
            col_str = ", ".join(keys)
            val_str = ", ".join(["%s"] * len(keys))
            insert_sql = f"INSERT INTO online_deals ({col_str}) VALUES ({val_str}) RETURNING id"
            result = fetch_one(insert_sql, tuple(deal_data.values()))
            if not result:
                raise ValueError("Failed to create online deal")
            created_id = result['id']

            return await self.get_online_deal_by_id(str(created_id))

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
            deal_data['updated_at'] = datetime.utcnow().isoformat()
            set_clauses = [f"{k} = %s" for k in deal_data.keys()]
            update_sql = f"UPDATE online_deals SET {', '.join(set_clauses)} WHERE id = %s"
            params = list(deal_data.values()) + [deal_id]
            rowcount = execute(update_sql, tuple(params))

            if rowcount == 0:
                return None

            return await self.get_online_deal_by_id(deal_id)

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
            execute(
                "UPDATE online_deals SET is_active = false, updated_at = %s WHERE id = %s",
                (datetime.utcnow().isoformat(), deal_id)
            )
            return True

        except Exception as e:
            logger.error(f"Error in delete_online_deal: {e}")
            raise
