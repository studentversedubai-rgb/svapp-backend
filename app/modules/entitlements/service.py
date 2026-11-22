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

import json
import secrets
import logging
from typing import List, Optional, Dict
from datetime import datetime, timedelta, timezone, time as dt_time
from decimal import Decimal
from app.core.database import fetch_one, fetch_all, execute, fetch_val
from app.core.redis import redis_manager
from app.core.activity import log_activity_event
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
    UserSavingsSummary,
    EntitlementStatusResponse
)
from app.shared.enums import EntitlementState
from app.shared.constants import (
    QR_PROOF_TOKEN_TTL_SECONDS,
    QR_TOKEN_LENGTH,
    REDIS_PREFIX_QR_TOKEN,
    REDIS_PREFIX_DAILY_CLAIM,
    BACKUP_CODE_ALPHABET,
    BACKUP_CODE_LENGTH,
    REDIS_PREFIX_BACKUP_CODE
)

logger = logging.getLogger(__name__)


class EntitlementService:
    """Handles entitlement operations"""

    def __init__(self):
        """Initialize service"""
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

        # Check frequency limit (Control 3)
        frequency = offer.get('frequency_per_student', 'daily')
        if not await self._check_frequency_limit(user_id, offer_id, frequency):
            raise ValueError("You've already used this offer recently.")

        # Check daily venue redemption cap (Control 2)
        daily_cap = offer.get('daily_redemption_cap')
        if daily_cap is not None:
            # Count today's CONFIRMED redemptions for this merchant
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            confirmed_today = fetch_val(
                "SELECT COUNT(*) FROM redemptions WHERE merchant_id = %s AND redeemed_at >= %s AND is_voided = false",
                (str(offer['merchant_id']), today_start.isoformat())
            ) or 0
            if confirmed_today >= daily_cap:
                raise ValueError("This offer has reached its daily limit.")

        # Check max total claims from the offer record
        max_total_claims = offer.get('max_total_claims')
        if max_total_claims is not None and offer.get('total_claims', 0) >= max_total_claims:
            raise ValueError("Offer claim limit reached")

        # Set expiry to end of day (timezone-naive for database)
        expires_at = datetime.combine(now_naive.date(), dt_time(23, 59, 59))

        # Create entitlement
        entitlement = fetch_one(
            "INSERT INTO entitlements (user_id, offer_id, device_id, state, claimed_at, expires_at) VALUES (%s, %s, %s, %s, %s, %s) RETURNING *",
            (user_id, offer_id, device_id, EntitlementState.ACTIVE.value, now.isoformat(), expires_at.isoformat())
        )

        if not entitlement:
            raise ValueError("Failed to create entitlement")

        # Increment offer claim count
        execute("UPDATE offers SET total_claims = COALESCE(total_claims, 0) + 1 WHERE id = %s", (offer_id,))

        # Log analytics event
        await self._log_analytics_event('offer_claim', {
            'user_id': user_id,
            'offer_id': offer_id,
            'entitlement_id': entitlement['id']
        })

        # Realtime user activity feed
        log_activity_event(
            user_id,
            "offer_claim",
            event_data={
                "offer_id": offer_id,
                "offer_title": offer.get("title"),
                "entitlement_id": entitlement["id"],
            },
        )

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

        # Generate secure random token for QR code
        proof_token = secrets.token_urlsafe(QR_TOKEN_LENGTH)

        # Generate 4-character backup code with up to 5 collision retries
        backup_code = None
        for _ in range(5):
            candidate = "".join(secrets.choice(BACKUP_CODE_ALPHABET) for _ in range(BACKUP_CODE_LENGTH))
            if not self.redis.get(f"{REDIS_PREFIX_BACKUP_CODE}{candidate}"):
                backup_code = candidate
                break

        if not backup_code:
            raise ValueError("Failed to generate a unique backup code. Please try again.")

        # Store in Redis with TTL
        redis_key = f"{REDIS_PREFIX_QR_TOKEN}{proof_token}"
        backup_key = f"{REDIS_PREFIX_BACKUP_CODE}{backup_code}"

        token_data = {
            'entitlement_id': entitlement_id,
            'user_id': user_id,
            'offer_id': entitlement['offer_id'],
            'device_id': entitlement.get('device_id'),
            'proof_token': proof_token,
            'backup_code': backup_code,
            'created_at': datetime.now().isoformat()
        }

        # Store both QR token and backup code in Redis with the same TTL
        serialized_data = json.dumps(token_data)
        self.redis.setex(redis_key, QR_PROOF_TOKEN_TTL_SECONDS, serialized_data)
        self.redis.setex(backup_key, QR_PROOF_TOKEN_TTL_SECONDS, serialized_data)

        expires_at_token = datetime.now() + timedelta(seconds=QR_PROOF_TOKEN_TTL_SECONDS)

        logger.info(f"QR proof token and backup code {backup_code} generated for entitlement {entitlement_id}")

        return GenerateProofResponse(
            proof_token=proof_token,
            backup_code=backup_code,
            expires_at=expires_at_token,
            ttl_seconds=QR_PROOF_TOKEN_TTL_SECONDS
        )

    # ================================
    # STUDENT STATUS (AMBER / GREEN)
    # ================================

    async def get_entitlement_status(
        self,
        entitlement_id: str,
        user_id: str
    ) -> EntitlementStatusResponse:
        """
        Return current UI state for the student's QR screen.

        Polls the DB state and maps it to:
          - "amber"    → cashier scanned, waiting for confirm
          - "green"    → cashier confirmed, show final amounts
          - "inactive" → anything else (active, expired, cancelled)
        """
        # 1. Fetch the entitlement
        entitlement = await self._get_entitlement(entitlement_id)
        if not entitlement:
            raise ValueError("Entitlement not found")

        # 2. Verify it belongs to this user
        if entitlement['user_id'] != user_id:
            raise ValueError("Unauthorized")

        state = entitlement['state']

        # 3. AMBER — cashier scanned, confirmation in progress
        if state == EntitlementState.PENDING_CONFIRMATION.value:
            return EntitlementStatusResponse(
                state=state,
                ui_state="amber"
            )

        # 4. GREEN — cashier confirmed, fetch amounts from redemptions table
        if state == EntitlementState.CONFIRMED.value:
            r = fetch_one(
                "SELECT * FROM redemptions WHERE entitlement_id = %s ORDER BY redeemed_at DESC LIMIT 1",
                (entitlement_id,)
            )

            if r:
                total_bill      = Decimal(str(r['total_bill_amount']))
                discount_amount = Decimal(str(r['discount_amount']))
                final_amount    = Decimal(str(r['final_amount']))
                return EntitlementStatusResponse(
                    state=state,
                    ui_state="green",
                    confirmed_at=datetime.fromisoformat(r['redeemed_at']),
                    total_bill=total_bill,
                    discount_amount=discount_amount,
                    amount_to_pay=final_amount,
                    savings=discount_amount
                )
            # redemption row not found yet (race condition) — stay amber
            return EntitlementStatusResponse(state=state, ui_state="amber")

        # 5. INACTIVE — active, expired, cancelled, anything else
        return EntitlementStatusResponse(state=state, ui_state="inactive")

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
        execute(
            "UPDATE entitlements SET state = %s, updated_at = %s WHERE id = %s",
            (EntitlementState.PENDING_CONFIRMATION.value, datetime.now().isoformat(), entitlement_id)
        )

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
        discounted_amount: Optional[Decimal] = None,
        requesting_user_id: Optional[str] = None
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

        # Block self-confirmation: student cannot confirm their own entitlement
        if requesting_user_id and entitlement['user_id'] == requesting_user_id:
            raise ValueError("Students cannot confirm their own redemptions")

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
        redemption = fetch_one(
            "INSERT INTO redemptions (entitlement_id, merchant_id, offer_id, user_id, total_bill_amount, discount_amount, final_amount, offer_type, redeemed_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
            (entitlement_id, offer['merchant_id'], offer['id'], entitlement['user_id'], float(total_bill_amount), float(discount_amount), float(final_amount), offer['offer_type'], now.isoformat())
        )

        if not redemption:
            raise ValueError("Failed to create redemption record")

        # Update entitlement state to CONFIRMED
        execute(
            "UPDATE entitlements SET state = %s, used_at = %s, updated_at = %s WHERE id = %s",
            (EntitlementState.CONFIRMED.value, now.isoformat(), now.isoformat(), entitlement_id)
        )

        # Log analytics event
        await self._log_analytics_event('redemption_confirmed', {
            'user_id': entitlement['user_id'],
            'offer_id': offer['id'],
            'merchant_id': offer['merchant_id'],
            'entitlement_id': entitlement_id,
            'redemption_id': redemption['id'],
            'savings': float(discount_amount)
        })

        # Realtime user activity feed
        merchant = await self._get_merchant(offer['merchant_id'])
        log_activity_event(
            entitlement['user_id'],
            "redemption",
            event_data={
                "offer_id": offer['id'],
                "offer_title": offer.get('title'),
                "merchant_name": (merchant or {}).get('name'),
                "entitlement_id": entitlement_id,
                "redemption_id": redemption['id'],
                "savings": float(discount_amount),
            },
        )

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

        # Verify the requesting user owns this entitlement
        if not user_id:
            raise ValueError("Unauthorized: authentication required")
        if entitlement['user_id'] != user_id:
            raise ValueError("Unauthorized: this entitlement does not belong to you")

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
        redemption = fetch_one(
            "SELECT * FROM redemptions WHERE entitlement_id = %s AND is_voided = false",
            (entitlement_id,)
        )

        if not redemption:
            raise ValueError("Redemption record not found")

        # Mark redemption as voided
        execute(
            "UPDATE redemptions SET is_voided = true, voided_at = %s, void_reason = %s, updated_at = %s WHERE id = %s",
            (now.isoformat(), reason, now.isoformat(), redemption['id'])
        )

        # Restore entitlement to CANCELLED (voided, not active)
        execute(
            "UPDATE entitlements SET state = %s, voided_at = %s, updated_at = %s WHERE id = %s",
            (EntitlementState.CANCELLED.value, now.isoformat(), now.isoformat(), entitlement_id)
        )

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
            query_sql = "SELECT * FROM entitlements WHERE user_id = %s"
            params = [user_id]
            if state_filter:
                query_sql += " AND state = %s"
                params.append(state_filter)
            query_sql += " ORDER BY claimed_at DESC"
            entitlements = fetch_all(query_sql, tuple(params))

            # Transform to list items
            items = []
            for ent in entitlements:
                row = fetch_one(
                    "SELECT o.title, m.name as merchant_name FROM offers o JOIN merchants m ON m.id = o.merchant_id WHERE o.id = %s",
                    (ent['offer_id'],)
                )

                if row:
                    offer_title = row['title']
                    merchant_name = row['merchant_name']
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
        rows = fetch_all(
            "SELECT total_bill_amount, discount_amount, final_amount FROM redemptions WHERE user_id = %s AND is_voided = false",
            (user_id,)
        )

        total_redemptions = len(rows)
        total_savings = sum(Decimal(str(r['discount_amount'])) for r in rows)
        total_spent = sum(Decimal(str(r['final_amount'])) for r in rows)

        return UserSavingsSummary(
            total_redemptions=total_redemptions,
            total_savings=total_savings,
            total_spent=total_spent
        )

    # ================================
    # HELPER METHODS
    # ================================

    async def _check_frequency_limit(
        self,
        user_id: str,
        offer_id: str,
        frequency: str
    ) -> bool:
        """
        Check if user has exceeded the offer's frequency limit.
        Returns True if claim is ALLOWED, False if user already redeemed within window.
        """
        now = datetime.now(timezone.utc)

        base_sql = "SELECT COUNT(*) FROM redemptions WHERE user_id = %s AND offer_id = %s AND is_voided = false"
        params = [str(user_id), str(offer_id)]

        if frequency == 'daily':
            # Today since 00:00:00 UTC
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            base_sql += " AND redeemed_at >= %s"
            params.append(start_of_day.isoformat())

        elif frequency == 'weekly':
            # Last 7 days
            seven_days_ago = now - timedelta(days=7)
            base_sql += " AND redeemed_at >= %s"
            params.append(seven_days_ago.isoformat())

        elif frequency == 'monthly':
            # Current calendar month (day 1)
            start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            base_sql += " AND redeemed_at >= %s"
            params.append(start_of_month.isoformat())

        elif frequency == 'quarterly':
            # Last 90 days
            ninety_days_ago = now - timedelta(days=90)
            base_sql += " AND redeemed_at >= %s"
            params.append(ninety_days_ago.isoformat())

        elif frequency == 'once_ever':
            # Any redemption ever, no date filter needed
            pass

        count = fetch_val(base_sql, tuple(params)) or 0

        # If count > 0, the student already used it within the frequency window!
        return count == 0

    async def _check_daily_limit(
        self,
        user_id: str,
        offer_id: str,
        max_claims_per_user: Optional[int]
    ) -> bool:
        """
        Atomically check and record daily claim using Redis INCR.
        Prevents TOCTOU race condition — no separate mark step needed.
        """
        if max_claims_per_user is None:
            return True  # No limit set

        today = datetime.now().date()
        redis_key = f"{REDIS_PREFIX_DAILY_CLAIM}{user_id}:{offer_id}:{today}"
        seconds_until_midnight = int((
            datetime.combine(today + timedelta(days=1), dt_time(0, 0, 0)) - datetime.now()
        ).total_seconds())

        if self.redis.redis_client:
            # Atomic increment — no race condition possible
            count = self.redis.redis_client.incr(redis_key)
            if count == 1:
                # First claim today — set TTL so key auto-expires at midnight
                self.redis.redis_client.expire(redis_key, seconds_until_midnight)
            if count > max_claims_per_user:
                # Over limit - roll back and reject
                self.redis.redis_client.decr(redis_key)
                return False
            return True
        else:
            # Memory fallback (dev only) - not fully atomic but acceptable
            entry = self.redis.memory_store.get(redis_key)
            current = int(entry[0]) if entry else 0
            if current >= max_claims_per_user:
                return False
            expiry = datetime.now().timestamp() + seconds_until_midnight
            self.redis.memory_store[redis_key] = (str(current + 1), expiry)
            return True

    async def _calculate_savings(
        self,
        offer: dict,
        total_bill: Decimal,
        discounted_amount: Optional[Decimal]
    ) -> tuple:
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

    async def _get_entitlement(self, entitlement_id: str) -> Optional[Dict]:
        return fetch_one("SELECT * FROM entitlements WHERE id = %s", (str(entitlement_id),))

    async def _get_offer(self, offer_id: str) -> Optional[Dict]:
        return fetch_one("SELECT * FROM offers WHERE id = %s", (str(offer_id),))

    async def _get_merchant(self, merchant_id: str) -> Optional[Dict]:
        return fetch_one("SELECT * FROM merchants WHERE id = %s", (str(merchant_id),))

    async def _get_user(self, user_id: str) -> Optional[Dict]:
        return fetch_one("SELECT name, first_name, last_name FROM users WHERE id = %s", (str(user_id),))

    async def _log_analytics_event(self, event_type: str, event_data: dict):
        """Log analytics event"""
        try:
            execute(
                "INSERT INTO analytics_events (event_type, event_data) VALUES (%s, %s::jsonb)",
                (event_type, json.dumps(event_data))
            )
        except Exception as e:
            logger.error(f"Failed to log analytics event: {e}")
            # Don't fail the main operation if analytics fails


# Global service instance
entitlement_service = EntitlementService()
