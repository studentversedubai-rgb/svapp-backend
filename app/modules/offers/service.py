"""
Offers Service

NO BUSINESS LOGIC - Structure only
"""


class OfferService:
    """Handles offer operations"""
    
    async def list_offers(self, filters: dict, page: int, page_size: int):
        """List offers with filters and pagination"""
        # TODO: Query offers from database
        # TODO: Apply filters (category, partner, search)
        # TODO: Return paginated results
        pass
    
    async def get_offer_by_id(self, offer_id: str):
        """Get offer details"""
        # TODO: Query offer from database
        # TODO: Include partner information
        pass
    
    async def claim_offer(self, offer_id: str, user_id: str):
        """
        Claim offer for user
        Creates entitlement in CLAIMED state
        """
        # TODO: Verify offer is active
        # TODO: Check user hasn't exceeded claim limit
        # TODO: Create entitlement (call entitlements service)
        pass
    
    async def check_user_can_claim(self, offer_id: str, user_id: str) -> bool:
        """Check if user can claim this offer"""
        # TODO: Check if offer is active
        # TODO: Check if user already claimed
        # TODO: Check max claims per user
        pass
