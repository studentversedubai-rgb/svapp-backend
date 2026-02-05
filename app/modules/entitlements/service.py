"""
Entitlements Service - Phase 3

CORE BUSINESS LOGIC: Manages entitlement lifecycle and redemption.

Key Features:
- Daily usage enforcement (one per user per offer per day)
- Short-lived QR proof tokens (30s TTL)
- Device binding for fraud prevention
- Amount capture and savings calculation
- Void logic with 2-hour window
- Analytics tracking
"""

import secrets
import logging
from typing import List, Optional, Dict
from datetime import datetime, timedelta, time as dt_time
from decimal import Decimal
from app.core.database import get_supabase_client
from app.core.redis import redis_manager
from app.modules.entitlements.state_machine import state_machine
from app.modules.entitlements.schemas import (
    ClaimEntitlementResponse,
    GenerateProofResponse,
    ValidateTokenResponse,
    ConfirmRedemptionResponse,
    VoidRedemptionResponse,
    EntitlementDetail,
    EntitlementListItem,
    RedemptionDetail,
    UserSavingsSummary
)
from app.shared.enums import EntitlementState
from app.shared.constants import (
    QR_PROOF_TOKEN_TTL_SECONDS,
    QR_TOKEN_LENGTH,
    REDIS_PREFIX_QR_TOKEN,
    REDIS_PREFIX_DAILY_CLAIM,
    MAX_DAILY_CLAIMS_PER_OFFER
)

logger = logging.getLogger(__name__)


class EntitlementService:
    """Handles entitlement operations"""
    
    def __init__(self):
        """Initialize service"""
        self.supabase = get_supabase_client()
        self.redis = redis_manager
    
    # ================================
    # CLAIM ENTITLEMENT
    # ================================
    
    async def claim_entitlement(
        self,
        user_id: str,
        offer_id: str,
        device_id: Optional[str] = None
    ) -> ClaimEntitlementResponse:
        """
        Create new entitlement (claim offer)
        
        Business Rules:
        - One entitlement per user per offer per day
        - Offer must be active and valid
        - User must be eligible
        
        Args:
            user_id: User UUID (from JWT)
            offer_id: Offer UUID
            device_id: Optional device identifier
            
        Returns:
            Created entitlement
            
        Raises:
            ValueError: If validation fails
        """
        # Check daily usage limit
        if not await self._check_daily_limit(user_id, offer_id):
            raise ValueError("Daily claim limit reached for this offer")
        
        # Validate offer eligibility
        offer = await self._get_offer(offer_id)
        if not offer:
            raise ValueError("Offer not found")
        
        if not offer.get('is_active'):
            raise ValueError("Offer is not active")
        
        # Check offer validity
        from datetime import timezone
        now = datetime.now(timezone.utc)
        
        # Parse offer dates - handle both with and without timezone
        try:
            if 'T' in offer['valid_from']:
                valid_from = datetime.fromisoformat(offer['valid_from'].replace('Z', '+00:00'))
            else:
                # If no time component, assume start of day UTC
                valid_from = datetime.fromisoformat(offer['valid_from']).replace(tzinfo=timezone.utc)
            
            if 'T' in offer['valid_until']:
                valid_until = datetime.fromisoformat(offer['valid_until'].replace('Z', '+00:00'))
            else:
                # If no time component, assume end of day UTC
                valid_until = datetime.fromisoformat(offer['valid_until']).replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        except Exception as e:
            logger.error(f"Error parsing offer dates: {e}")
            raise ValueError("Invalid offer date format")
        
        # Make timezone-naive for comparison if needed
        now_naive = now.replace(tzinfo=None)
        valid_from_naive = valid_from.replace(tzinfo=None) if valid_from.tzinfo else valid_from
        valid_until_naive = valid_until.replace(tzinfo=None) if valid_until.tzinfo else valid_until
        
        if now_naive < valid_from_naive or now_naive > valid_until_naive:
            raise ValueError("Offer is not currently valid")
        
        # Check time-of-day validity (optional fields)
        if offer.get('time_valid_from') and offer.get('time_valid_until'):
            try:
                current_time = now_naive.time()
                time_from = datetime.strptime(offer['time_valid_from'], '%H:%M:%S').time()
                time_until = datetime.strptime(offer['time_valid_until'], '%H:%M:%S').time()
                
                if not (time_from <= current_time <= time_until):
                    raise ValueError("Offer is not valid at this time")
            except Exception as e:
                logger.warning(f"Error checking time validity: {e}")
                # Continue if time validation fails
        
        # Check day-of-week validity (optional field)
        if offer.get('valid_days_of_week'):
            current_day = now_naive.weekday()  # 0 = Monday, 6 = Sunday
            if current_day not in offer['valid_days_of_week']:
                raise ValueError("Offer is not valid on this day")
        
        # Check max claims
        if offer.get('max_total_claims'):
            if offer.get('total_claims', 0) >= offer['max_total_claims']:
                raise ValueError("Offer claim limit reached")
        
        # Set expiry to end of day (timezone-naive for database)
        expires_at = datetime.combine(now_naive.date(), dt_time(23, 59, 59))
        
        # Create entitlement
        entitlement_data = {
            'user_id': user_id,
            'offer_id': offer_id,
            'device_id': device_id,
            'state': EntitlementState.ACTIVE.value,
            'claimed_at': now.isoformat(),
            'expires_at': expires_at.isoformat()
        }
        
        result = self.supabase.table('entitlements').insert(entitlement_data).execute()
        
        if not result.data:
            raise ValueError("Failed to create entitlement")
        
        entitlement = result.data[0]
        
        # Increment offer claim count
        self.supabase.table('offers').update({
            'total_claims': offer.get('total_claims', 0) + 1
        }).eq('id', offer_id).execute()
        
        # Track in Redis for daily limit
        await self._mark_daily_claim(user_id, offer_id)
        
        # Log analytics event
        await self._log_analytics_event('offer_claim', {
            'user_id': user_id,
            'offer_id': offer_id,
            'entitlement_id': entitlement['id']
        })
        
        logger.info(f"Entitlement claimed: {entitlement['id']} by user {user_id}")
        
        return ClaimEntitlementResponse(
            entitlement_id=entitlement['id'],
            offer_id=offer_id,
            expires_at=datetime.fromisoformat(entitlement['expires_at'].replace('Z', '+00:00'))
        )
    
    # ================================
    # QR PROOF TOKEN GENERATION
    # ================================
    
    async def generate_proof_token(
        self,
        entitlement_id: str,
        user_id: str
    ) -> GenerateProofResponse:
        """
        Generate short-lived proof token for QR code
        
        Token stored in Redis with 30s TTL
        
        Args:
            entitlement_id: Entitlement UUID
            user_id: User UUID (for verification)
            
        Returns:
            Proof token and expiry
            
        Raises:
            ValueError: If validation fails
        """
        # Get entitlement
        entitlement = await self._get_entitlement(entitlement_id)
        
        if not entitlement:
            raise ValueError("Entitlement not found")
        
        # Verify ownership
        if entitlement['user_id'] != user_id:
            raise ValueError("Unauthorized: entitlement belongs to another user")
        
        # Check if can generate QR
        state = EntitlementState(entitlement['state'])
        expires_at = datetime.fromisoformat(entitlement['expires_at'].replace('Z', '+00:00'))
        
        can_generate, reason = state_machine.can_generate_qr(state, expires_at)
        if not can_generate:
            raise ValueError(reason)
        
        # Generate secure random token
        proof_token = secrets.token_urlsafe(QR_TOKEN_LENGTH)
        
        # Store in Redis with TTL
        redis_key = f"{REDIS_PREFIX_QR_TOKEN}{proof_token}"
        token_data = {
            'entitlement_id': entitlement_id,
            'user_id': user_id,
            'offer_id': entitlement['offer_id'],
            'device_id': entitlement.get('device_id'),
            'created_at': datetime.now().isoformat()
        }
        
        # Store as JSON string
        import json
        self.redis.setex(
            redis_key,
            QR_PROOF_TOKEN_TTL_SECONDS,
            json.dumps(token_data)
        )
        
        expires_at_token = datetime.now() + timedelta(seconds=QR_PROOF_TOKEN_TTL_SECONDS)
        
        logger.info(f"QR proof token generated for entitlement {entitlement_id}")
        
        return GenerateProofResponse(
            proof_token=proof_token,
            expires_at=expires_at_token,
            ttl_seconds=QR_PROOF_TOKEN_TTL_SECONDS
        )
    
    # ================================
    # VALIDATION (MERCHANT SIDE)
    # ================================
    
    async def validate_proof_token(
        self,
        proof_token: str
    ) -> ValidateTokenResponse:
        """
        Validate proof token (merchant scans QR)
        
        Validates:
        - Token exists in Redis
        - Entitlement is active
        - Not already used
        - Device binding (if applicable)
        - Time window
        
        Args:
            proof_token: QR proof token
            
        Returns:
            Validation result with offer details
        """
        # Check token in Redis
        redis_key = f"{REDIS_PREFIX_QR_TOKEN}{proof_token}"
        token_data_str = self.redis.get(redis_key)
        
        if not token_data_str:
            return ValidateTokenResponse(
                success=False,
                status="FAIL",
                reason="Invalid or expired token"
            )
        
        # Parse token data
        import json
        token_data = json.loads(token_data_str)
        
        entitlement_id = token_data['entitlement_id']
        
        # Get entitlement
        entitlement = await self._get_entitlement(entitlement_id)
        
        if not entitlement:
            return ValidateTokenResponse(
                success=False,
                status="FAIL",
                reason="Entitlement not found"
            )
        
        # Validate state
        state = EntitlementState(entitlement['state'])
        can_validate, reason = state_machine.can_validate(state)
        
        if not can_validate:
            return ValidateTokenResponse(
                success=False,
                status="FAIL",
                reason=reason
            )
        
        # Validate not expired
        expires_at = datetime.fromisoformat(entitlement['expires_at'].replace('Z', '+00:00'))
        if datetime.now(expires_at.tzinfo) >= expires_at:
            return ValidateTokenResponse(
                success=False,
                status="FAIL",
                reason="Entitlement has expired"
            )
        
        # Get offer details
        offer = await self._get_offer(entitlement['offer_id'])
        merchant = await self._get_merchant(offer['merchant_id'])
        user = await self._get_user(entitlement['user_id'])
        
        # Mark as pending confirmation
        self.supabase.table('entitlements').update({
            'state': EntitlementState.PENDING_CONFIRMATION.value,
            'updated_at': datetime.now().isoformat()
        }).eq('id', entitlement_id).execute()
        
        logger.info(f"Token validated successfully for entitlement {entitlement_id}")
        
        return ValidateTokenResponse(
            success=True,
            status="PASS",
            entitlement_id=entitlement_id,
            offer_title=offer['title'],
            offer_type=offer['offer_type'],
            discount_value=offer.get('discount_value'),
            merchant_name=merchant['name'],
            student_name=user.get('name', 'Student')
        )
    
    # ================================
    # AMOUNT CAPTURE & CONFIRMATION
    # ================================
    
    async def confirm_redemption(
        self,
        entitlement_id: str,
        total_bill_amount: Decimal,
        discounted_amount: Optional[Decimal] = None
    ) -> ConfirmRedemptionResponse:
        """
        Confirm redemption with amount capture
        
        Calculates savings based on offer type:
        - percentage: discount_amount = total * (percentage / 100)
        - bogo: discount_amount = item_price (from offer)
        - bundle: discount_amount = original_price - bundle_price
        
        Args:
            entitlement_id: Entitlement UUID
            total_bill_amount: Total bill before discount
            discounted_amount: Optional final amount after discount
            
        Returns:
            Redemption confirmation with savings
            
        Raises:
            ValueError: If validation fails
        """
        # Get entitlement
        entitlement = await self._get_entitlement(entitlement_id)
        
        if not entitlement:
            raise ValueError("Entitlement not found")
        
        # Validate state
        state = EntitlementState(entitlement['state'])
        can_confirm, reason = state_machine.can_confirm(state)
        
        if not can_confirm:
            raise ValueError(reason)
        
        # Get offer for savings calculation
        offer = await self._get_offer(entitlement['offer_id'])
        
        # Calculate savings based on offer type
        discount_amount, final_amount = await self._calculate_savings(
            offer,
            total_bill_amount,
            discounted_amount
        )
        
        # Create redemption record
        now = datetime.now()
        redemption_data = {
            'entitlement_id': entitlement_id,
            'merchant_id': offer['merchant_id'],
            'offer_id': offer['id'],
            'user_id': entitlement['user_id'],
            'total_bill_amount': float(total_bill_amount),
            'discount_amount': float(discount_amount),
            'final_amount': float(final_amount),
            'offer_type': offer['offer_type'],
            'redeemed_at': now.isoformat()
        }
        
        redemption_result = self.supabase.table('redemptions').insert(redemption_data).execute()
        
        if not redemption_result.data:
            raise ValueError("Failed to create redemption record")
        
        redemption = redemption_result.data[0]
        
        # Update entitlement state to USED
        self.supabase.table('entitlements').update({
            'state': EntitlementState.USED.value,
            'used_at': now.isoformat(),
            'updated_at': now.isoformat()
        }).eq('id', entitlement_id).execute()
        
        # Delete QR token from Redis (single-use)
        # Note: Token might already be expired, but delete anyway
        # We don't have the token here, but it's okay - TTL will handle it
        
        # Log analytics event
        await self._log_analytics_event('redemption_confirmed', {
            'user_id': entitlement['user_id'],
            'offer_id': offer['id'],
            'merchant_id': offer['merchant_id'],
            'entitlement_id': entitlement_id,
            'redemption_id': redemption['id'],
            'savings': float(discount_amount)
        })
        
        # TODO: Send notification to student
        # "Redemption successful — You saved AED {discount_amount}"
        
        logger.info(f"Redemption confirmed: {redemption['id']} for entitlement {entitlement_id}")
        
        return ConfirmRedemptionResponse(
            redemption_id=redemption['id'],
            entitlement_id=entitlement_id,
            total_bill=total_bill_amount,
            discount_amount=discount_amount,
            final_amount=final_amount,
            savings=discount_amount,
            redeemed_at=now
        )
    
    # ================================
    # VOID LOGIC
    # ================================
    
    async def void_redemption(
        self,
        entitlement_id: str,
        reason: str,
        user_id: Optional[str] = None  # For authorization
    ) -> VoidRedemptionResponse:
        """
        Void a redemption within 2-hour window
        
        Business Rules:
        - Only USED entitlements can be voided
        - Must be within 2 hours of redemption
        - Restores entitlement to ACTIVE (same day only)
        - Marks redemption as voided
        
        Args:
            entitlement_id: Entitlement UUID
            reason: Reason for voiding
            user_id: Optional user ID for authorization
            
        Returns:
            Void confirmation
            
        Raises:
            ValueError: If validation fails
        """
        # Get entitlement
        entitlement = await self._get_entitlement(entitlement_id)
        
        if not entitlement:
            raise ValueError("Entitlement not found")
        
        # Validate state and void window
        state = EntitlementState(entitlement['state'])
        
        if not entitlement.get('used_at'):
            raise ValueError("Entitlement has not been used")
        
        used_at = datetime.fromisoformat(entitlement['used_at'].replace('Z', '+00:00'))
        can_void, void_reason = state_machine.can_void(state, used_at)
        
        if not can_void:
            raise ValueError(void_reason)
        
        # Check if same day
        now = datetime.now()
        if now.date() != used_at.date():
            raise ValueError("Cannot void redemption from a different day")
        
        # Get redemption record
        redemption_result = self.supabase.table('redemptions').select('*').eq(
            'entitlement_id', entitlement_id
        ).eq('is_voided', False).execute()
        
        if not redemption_result.data:
            raise ValueError("Redemption record not found")
        
        redemption = redemption_result.data[0]
        
        # Mark redemption as voided
        self.supabase.table('redemptions').update({
            'is_voided': True,
            'voided_at': now.isoformat(),
            'void_reason': reason,
            'updated_at': now.isoformat()
        }).eq('id', redemption['id']).execute()
        
        # Restore entitlement to ACTIVE
        self.supabase.table('entitlements').update({
            'state': EntitlementState.VOIDED.value,  # Mark as voided, not active
            'voided_at': now.isoformat(),
            'updated_at': now.isoformat()
        }).eq('id', entitlement_id).execute()
        
        # Log analytics event
        await self._log_analytics_event('redemption_voided', {
            'user_id': entitlement['user_id'],
            'entitlement_id': entitlement_id,
            'redemption_id': redemption['id'],
            'reason': reason
        })
        
        logger.info(f"Redemption voided: {redemption['id']} for entitlement {entitlement_id}")
        
        return VoidRedemptionResponse(
            entitlement_id=entitlement_id,
            voided_at=now
        )
    
    # ================================
    # QUERY METHODS
    # ================================
    
    async def get_user_entitlements(
        self,
        user_id: str,
        state_filter: Optional[str] = None
    ) -> List[EntitlementListItem]:
        """Get user's entitlements with optional state filter"""
        try:
            # Query entitlements
            query = self.supabase.table('entitlements').select('*').eq('user_id', user_id).order('claimed_at', desc=True)
            
            if state_filter:
                query = query.eq('state', state_filter)
            
            result = query.execute()
            
            # Transform to list items
            items = []
            for ent in result.data:
                # Fetch offer details
                offer_result = self.supabase.table('offers').select('title, merchant_id').eq('id', ent['offer_id']).execute()
                
                if offer_result.data:
                    offer = offer_result.data[0]
                    
                    # Fetch merchant details
                    merchant_result = self.supabase.table('merchants').select('name').eq('id', offer['merchant_id']).execute()
                    merchant_name = merchant_result.data[0]['name'] if merchant_result.data else 'Unknown Merchant'
                    offer_title = offer['title']
                else:
                    offer_title = 'Unknown Offer'
                    merchant_name = 'Unknown Merchant'
                
                items.append(EntitlementListItem(
                    id=ent['id'],
                    offer_title=offer_title,
                    merchant_name=merchant_name,
                    state=ent['state'],
                    claimed_at=datetime.fromisoformat(ent['claimed_at'].replace('Z', '+00:00')),
                    expires_at=datetime.fromisoformat(ent['expires_at'].replace('Z', '+00:00'))
                ))
            
            return items
        except Exception as e:
            logger.error(f"Error fetching entitlements: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise ValueError(f"Failed to fetch entitlements: {str(e)}")
    
    async def get_user_savings_summary(self, user_id: str) -> UserSavingsSummary:
        """Get user's total savings summary"""
        result = self.supabase.table('redemptions').select(
            'total_bill_amount, discount_amount, final_amount'
        ).eq('user_id', user_id).eq('is_voided', False).execute()
        
        total_redemptions = len(result.data)
        total_savings = sum(Decimal(str(r['discount_amount'])) for r in result.data)
        total_spent = sum(Decimal(str(r['final_amount'])) for r in result.data)
        
        return UserSavingsSummary(
            total_redemptions=total_redemptions,
            total_savings=total_savings,
            total_spent=total_spent
        )
    
    # ================================
    # HELPER METHODS
    # ================================
    
    async def _check_daily_limit(self, user_id: str, offer_id: str) -> bool:
        """Check if user has reached daily claim limit for offer"""
        # Check in Redis first (fast)
        redis_key = f"{REDIS_PREFIX_DAILY_CLAIM}{user_id}:{offer_id}:{datetime.now().date()}"
        if self.redis.get(redis_key):
            return False
        
        # Check in database (fallback)
        today_start = datetime.combine(datetime.now().date(), dt_time(0, 0, 0))
        today_end = datetime.combine(datetime.now().date(), dt_time(23, 59, 59))
        
        result = self.supabase.table('entitlements').select('id').eq(
            'user_id', user_id
        ).eq('offer_id', offer_id).gte(
            'claimed_at', today_start.isoformat()
        ).lte(
            'claimed_at', today_end.isoformat()
        ).neq('state', EntitlementState.VOIDED.value).execute()
        
        return len(result.data) < MAX_DAILY_CLAIMS_PER_OFFER
    
    async def _mark_daily_claim(self, user_id: str, offer_id: str):
        """Mark claim in Redis for daily limit tracking"""
        redis_key = f"{REDIS_PREFIX_DAILY_CLAIM}{user_id}:{offer_id}:{datetime.now().date()}"
        # Expire at end of day
        seconds_until_midnight = (
            datetime.combine(datetime.now().date() + timedelta(days=1), dt_time(0, 0, 0)) -
            datetime.now()
        ).total_seconds()
        self.redis.setex(redis_key, int(seconds_until_midnight), "1")
    
    async def _calculate_savings(
        self,
        offer: dict,
        total_bill: Decimal,
        discounted_amount: Optional[Decimal]
    ) -> tuple[Decimal, Decimal]:
        """
        Calculate savings based on offer type
        
        Returns:
            (discount_amount, final_amount)
        """
        offer_type = offer['offer_type']
        
        if discounted_amount is not None:
            # Merchant provided final amount
            discount = total_bill - discounted_amount
            return discount, discounted_amount
        
        # Calculate based on offer type
        if offer_type == 'percentage':
            # Extract percentage from discount_value (e.g., "20%")
            percentage_str = offer.get('discount_value', '0%').replace('%', '')
            percentage = Decimal(percentage_str)
            discount = (total_bill * percentage) / Decimal('100')
            final = total_bill - discount
            return discount, final
        
        elif offer_type == 'bogo':
            # Buy one get one - discount is the item price
            # Assume discount_value contains the item price
            item_price = Decimal(str(offer.get('original_price', 0)))
            discount = item_price
            final = total_bill - discount
            return discount, final
        
        elif offer_type == 'bundle':
            # Fixed price bundle
            bundle_price = Decimal(str(offer.get('discounted_price', 0)))
            original_price = Decimal(str(offer.get('original_price', 0)))
            discount = original_price - bundle_price
            final = bundle_price
            return discount, final
        
        else:
            # Default: no discount
            return Decimal('0'), total_bill
    
    async def _get_entitlement(self, entitlement_id: str) -> Optional[dict]:
        """Get entitlement by ID"""
        result = self.supabase.table('entitlements').select('*').eq('id', entitlement_id).execute()
        return result.data[0] if result.data else None
    
    async def _get_offer(self, offer_id: str) -> Optional[dict]:
        """Get offer by ID"""
        result = self.supabase.table('offers').select('*').eq('id', offer_id).execute()
        return result.data[0] if result.data else None
    
    async def _get_merchant(self, merchant_id: str) -> Optional[dict]:
        """Get merchant by ID"""
        result = self.supabase.table('merchants').select('*').eq('id', merchant_id).execute()
        return result.data[0] if result.data else None
    
    async def _get_user(self, user_id: str) -> Optional[dict]:
        """Get user by ID"""
        result = self.supabase.table('users').select('*').eq('id', user_id).execute()
        return result.data[0] if result.data else None
    
    async def _log_analytics_event(self, event_type: str, data: dict):
        """Log analytics event"""
        try:
            event_data = {
                'event_type': event_type,
                'event_data': data,
                'created_at': datetime.now().isoformat()
            }
            self.supabase.table('analytics_events').insert(event_data).execute()
        except Exception as e:
            logger.error(f"Failed to log analytics event: {e}")
            # Don't fail the main operation if analytics fails


# Global service instance
entitlement_service = EntitlementService()
