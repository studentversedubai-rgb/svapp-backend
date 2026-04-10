"""
Merchant Validation Service

Handles merchant-side QR validation, confirmation, and void operations.
Does NOT require student JWT authentication.
"""

import json
import logging
import os
import re
import hashlib
import hmac
from typing import Optional, Dict
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import UUID

os.environ.setdefault("PASSLIB_BUILTIN_BCRYPT", "enabled")

from passlib.hash import bcrypt as bcrypt_hasher

from app.core.database import get_supabase_client
from app.core.redis import redis_manager
from app.modules.merchant.schemas import (
    MerchantValidateResponse,
    MerchantConfirmResponse,
    MerchantVoidResponse
)
from app.shared.enums import EntitlementState
from app.shared.constants import (
    REDIS_PREFIX_QR_TOKEN,
    VOID_WINDOW_HOURS
)

logger = logging.getLogger(__name__)


class MerchantService:
    """Handles merchant validation operations"""
    
    def __init__(self):
        """Initialize service"""
        self.supabase = get_supabase_client()
        self.redis = redis_manager
    
    # ================================
    # VALIDATE QR TOKEN
    # ================================
    
    async def validate_proof_token(self, proof_token: str) -> MerchantValidateResponse:
        """
        Validate student's QR proof token
        
        Args:
            proof_token: QR proof token from student
            
        Returns:
            Validation response with PASS/FAIL status
        """
        try:
            # Get token data from Redis
            redis_key = f"{REDIS_PREFIX_QR_TOKEN}{proof_token}"
            token_data_str = self.redis.get(redis_key)
            
            if not token_data_str:
                return MerchantValidateResponse(
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
                return MerchantValidateResponse(
                    success=False,
                    status="FAIL",
                    reason="Entitlement not found"
                )
            
            # Check entitlement state — accept ACTIVE or PENDING_CONFIRMATION
            # (PENDING_CONFIRMATION means it was validated but not yet confirmed)
            if entitlement['state'] not in [
                EntitlementState.ACTIVE.value,
                EntitlementState.PENDING_CONFIRMATION.value
            ]:
                state_val = entitlement['state']
                if state_val == EntitlementState.USED.value:
                    reason = "This offer has already been redeemed"
                elif state_val == EntitlementState.EXPIRED.value:
                    reason = "Entitlement has expired"
                elif state_val == EntitlementState.VOIDED.value:
                    reason = "Entitlement has been voided"
                else:
                    reason = f"Entitlement is {state_val}"
                return MerchantValidateResponse(
                    success=False,
                    status="FAIL",
                    reason=reason
                )
            
            # Check expiry
            expires_at = datetime.fromisoformat(entitlement['expires_at'].replace('Z', '+00:00'))
            if datetime.now(timezone.utc) > expires_at:
                return MerchantValidateResponse(
                    success=False,
                    status="FAIL",
                    reason="Entitlement expired"
                )
            
            # Get offer details
            offer = await self._get_offer(entitlement['offer_id'])
            if not offer:
                return MerchantValidateResponse(
                    success=False,
                    status="FAIL",
                    reason="Offer not found"
                )
            
            # Get merchant details
            merchant = await self._get_merchant(offer['merchant_id'])
            merchant_name = merchant['name'] if merchant else "Unknown Merchant"
            
            # Get user details
            user = await self._get_user(entitlement['user_id'])
            student_name = user.get('full_name', 'Student') if user else "Student"

            # Extend the Redis token TTL to give the merchant time to enter
            # their PIN and bill amount (default QR TTL is only 30 seconds).
            # 300 seconds = 5 minutes is sufficient for the merchant flow.
            # RedisManager only exposes setex/get/delete, so we re-store
            # the same token data with the new TTL instead of calling expire.
            MERCHANT_SESSION_TTL = 300
            self.redis.setex(redis_key, MERCHANT_SESSION_TTL, token_data_str)

            # Mark entitlement as PENDING_CONFIRMATION so concurrent scans are rejected
            self.supabase.table('entitlements').update({
                'state': EntitlementState.PENDING_CONFIRMATION.value,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }).eq('id', str(entitlement_id)).execute()

            logger.info(
                f"QR token validated for entitlement {entitlement_id}; "
                f"TTL extended to {MERCHANT_SESSION_TTL}s"
            )
            
            # Return PASS with details
            return MerchantValidateResponse(
                success=True,
                status="PASS",
                entitlement_id=entitlement_id,
                offer_title=offer['title'],
                offer_type=offer['offer_type'],
                discount_value=offer.get('discount_value'),
                merchant_name=merchant_name,
                student_name=student_name,
                original_price=offer.get('original_price'),
                discounted_price=offer.get('discounted_price')
            )
            
        except Exception as e:
            logger.error(f"Error validating proof token: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return MerchantValidateResponse(
                success=False,
                status="FAIL",
                reason="Validation error"
            )
    
    # ================================
    # CONFIRM REDEMPTION
    # ================================
    
    async def confirm_redemption(
        self,
        proof_token: str,
        merchant_pin: str,
        total_bill_amount: Decimal
    ) -> MerchantConfirmResponse:
        """
        Confirm redemption with bill amount
        
        Args:
            proof_token: QR proof token
            merchant_pin: Merchant PIN for authentication
            total_bill_amount: Total bill before discount
            
        Returns:
            Confirmation response with savings details
            
        Raises:
            ValueError: If validation fails
        """
        # Get token data from Redis
        redis_key = f"{REDIS_PREFIX_QR_TOKEN}{proof_token}"
        token_data_str = self.redis.get(redis_key)
        
        if not token_data_str:
            raise ValueError("Invalid or expired token")
        
        # Parse token data
        token_data = json.loads(token_data_str)
        entitlement_id = token_data['entitlement_id']
        
        # Get entitlement
        entitlement = await self._get_entitlement(entitlement_id)
        if not entitlement:
            raise ValueError("Entitlement not found")
        
        # Check state
        if entitlement['state'] not in [EntitlementState.ACTIVE.value, EntitlementState.PENDING_CONFIRMATION.value]:
            if entitlement['state'] == EntitlementState.USED.value:
                raise ValueError("This entitlement has already been redeemed.")
            elif entitlement['state'] == EntitlementState.EXPIRED.value:
                raise ValueError("This entitlement has expired.")
            elif entitlement['state'] == EntitlementState.VOIDED.value:
                raise ValueError("This entitlement has been voided.")
            else:
                raise ValueError(f"Entitlement cannot be confirmed (state: {entitlement['state']})")
        
        # Get offer
        offer = await self._get_offer(entitlement['offer_id'])
        if not offer:
            raise ValueError("Offer not found")
        
        # Validate merchant PIN
        merchant = await self._get_merchant(offer['merchant_id'])
        if not merchant:
            raise ValueError("Merchant not found")
        
        if not await self._verify_merchant_pin(merchant['id'], merchant_pin):
            raise ValueError("Invalid merchant PIN")
        
        # Calculate discount and final amount
        discount_amount, final_amount = self._calculate_savings(
            offer['offer_type'],
            total_bill_amount,
            offer.get('discount_value'),
            offer.get('original_price'),
            offer.get('discounted_price')
        )
        
        # Create redemption record
        redemption_data = {
            'entitlement_id': str(entitlement_id),
            'merchant_id': str(offer['merchant_id']),
            'offer_id': str(entitlement['offer_id']),
            'user_id': str(entitlement['user_id']),
            'total_bill_amount': float(total_bill_amount),
            'discount_amount': float(discount_amount),
            'final_amount': float(final_amount),
            'offer_type': offer['offer_type'],
            'redeemed_at': datetime.now(timezone.utc).isoformat(),
            'is_voided': False
        }
        
        result = self.supabase.table('redemptions').insert(redemption_data).execute()
        
        if not result.data:
            raise ValueError("Failed to create redemption")
        
        redemption = result.data[0]
        
        # Mark entitlement as USED
        self.supabase.table('entitlements').update({
            'state': EntitlementState.USED.value,
            'used_at': datetime.now(timezone.utc).isoformat()
        }).eq('id', str(entitlement_id)).execute()
        
        # Delete Redis token (single-use)
        self.redis.delete(redis_key)
        
        # Log analytics
        await self._log_analytics_event('redemption_confirmed', {
            'redemption_id': redemption['id'],
            'merchant_id': str(offer['merchant_id']),
            'offer_id': str(entitlement['offer_id']),
            'savings': float(discount_amount)
        })
        
        return MerchantConfirmResponse(
            success=True,
            message="Redemption confirmed successfully",
            redemption_id=redemption['id'],
            entitlement_id=entitlement_id,
            total_bill=total_bill_amount,
            discount_amount=discount_amount,
            final_amount=final_amount,
            savings=discount_amount,
            redeemed_at=datetime.fromisoformat(redemption['redeemed_at'].replace('Z', '+00:00'))
        )
    
    # ================================
    # VOID REDEMPTION
    # ================================
    
    async def void_redemption(
        self,
        redemption_id: UUID,
        merchant_pin: str,
        reason: str
    ) -> MerchantVoidResponse:
        """
        Void a redemption within the void window
        
        Args:
            redemption_id: Redemption to void
            merchant_pin: Merchant PIN for authentication
            reason: Void reason
            
        Returns:
            Void response
            
        Raises:
            ValueError: If validation fails
        """
        # Get redemption
        redemption = await self._get_redemption(redemption_id)
        if not redemption:
            raise ValueError("Redemption not found")
        
        if redemption['is_voided']:
            raise ValueError("Redemption already voided")
        
        # Validate merchant PIN
        if not await self._verify_merchant_pin(redemption['merchant_id'], merchant_pin):
            raise ValueError("Invalid merchant PIN")
        
        # Check void window (2 hours)
        redeemed_at = datetime.fromisoformat(redemption['redeemed_at'].replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        time_since_redemption = now - redeemed_at
        
        if time_since_redemption > timedelta(hours=VOID_WINDOW_HOURS):
            raise ValueError(f"Void window expired. Must void within {VOID_WINDOW_HOURS} hours")
        
        # Check same day
        if redeemed_at.date() != now.date():
            raise ValueError("Voiding only allowed on same day of redemption")
        
        # Mark redemption as voided
        self.supabase.table('redemptions').update({
            'is_voided': True,
            'voided_at': now.isoformat(),
            'void_reason': reason
        }).eq('id', str(redemption_id)).execute()
        
        # Restore entitlement to ACTIVE (if same day)
        self.supabase.table('entitlements').update({
            'state': EntitlementState.VOIDED.value,
            'voided_at': now.isoformat()
        }).eq('id', str(redemption['entitlement_id'])).execute()
        
        # Log analytics
        await self._log_analytics_event('redemption_voided', {
            'redemption_id': str(redemption_id),
            'reason': reason
        })
        
        return MerchantVoidResponse(
            success=True,
            message="Redemption voided successfully",
            redemption_id=redemption_id,
            voided_at=now
        )
    
    # ================================
    # HELPER METHODS
    # ================================
    
    async def _get_entitlement(self, entitlement_id: str) -> Optional[Dict]:
        """Get entitlement by ID"""
        result = self.supabase.table('entitlements').select('*').eq('id', entitlement_id).execute()
        return result.data[0] if result.data else None
    
    async def _get_offer(self, offer_id: str) -> Optional[Dict]:
        """Get offer by ID"""
        result = self.supabase.table('offers').select('*').eq('id', offer_id).execute()
        return result.data[0] if result.data else None
    
    async def _get_merchant(self, merchant_id: str) -> Optional[Dict]:
        """Get merchant by ID"""
        result = self.supabase.table('merchants').select('*').eq('id', merchant_id).execute()
        return result.data[0] if result.data else None
    
    async def _get_user(self, user_id: str) -> Optional[Dict]:
        """Get user profile"""
        try:
            result = self.supabase.table('users').select('first_name, last_name, name').eq('id', user_id).execute()
            if result.data:
                u = result.data[0]
                # Build display name from available fields
                full_name = u.get('name') or ' '.join(filter(None, [u.get('first_name'), u.get('last_name')])) or 'Student'
                return {'full_name': full_name}
            return None
        except:
            return None
    
    async def _get_redemption(self, redemption_id: UUID) -> Optional[Dict]:
        """Get redemption by ID"""
        result = self.supabase.table('redemptions').select('*').eq('id', str(redemption_id)).execute()
        return result.data[0] if result.data else None
    
    async def _verify_merchant_pin(self, merchant_id: str, pin: str) -> bool:
        """
        Verify merchant PIN
        
        Merchant PINs are stored as bcrypt hashes in merchants.pin_hash.
        """
        try:
            merchant = await self._get_merchant(merchant_id)
            if not merchant:
                return False
            
            stored_hash = merchant.get('pin_hash')
            if not stored_hash:
                logger.warning(f"No PIN hash for merchant {merchant_id}")
                return False

            # Support both bcrypt and SHA256 hashes to match existing data.
            if stored_hash.startswith('$2a$') or stored_hash.startswith('$2b$') or stored_hash.startswith('$2y$'):
                return bcrypt_hasher.verify(pin, stored_hash)

            if re.fullmatch(r"[0-9a-fA-F]{64}", stored_hash):
                pin_hash = hashlib.sha256(pin.encode('utf-8')).hexdigest()
                return hmac.compare_digest(pin_hash, stored_hash.lower())

            # Fallback: try bcrypt verification for any other format.
            return bcrypt_hasher.verify(pin, stored_hash)
        except Exception as e:
            logger.error(f"Error verifying merchant PIN: {e}")
            return False
    
    def _calculate_savings(
        self,
        offer_type: str,
        total_bill: Decimal,
        discount_value: Optional[str],
        original_price: Optional[Decimal],
        discounted_price: Optional[Decimal]
    ) -> tuple[Decimal, Decimal]:
        """
        Calculate discount amount and final bill
        
        Returns:
            (discount_amount, final_amount)
        """
        if offer_type == 'percentage':
            # Extract numeric percentage from discount_value like "20%" or "20% off".
            raw_value = '' if discount_value is None else str(discount_value)
            match = re.search(r"\d+(?:\.\d+)?", raw_value)
            if not match:
                logger.error(
                    f"Cannot extract percentage from discount_value={discount_value!r}. "
                    "Applying zero discount as safe fallback."
                )
                # Return zero discount rather than crashing the entire redemption
                return Decimal('0'), total_bill
            percentage = Decimal(match.group(0))
            discount_amount = (total_bill * percentage) / Decimal('100')
            final_amount = total_bill - discount_amount
            
        elif offer_type == 'bogo':
            # Buy 1 Get 1: discount is the item price
            discount_amount = Decimal(str(original_price)) if original_price else Decimal('0')
            final_amount = total_bill - discount_amount
            
        elif offer_type == 'bundle':
            # Fixed price bundle
            if original_price and discounted_price:
                discount_amount = Decimal(str(original_price)) - Decimal(str(discounted_price))
                final_amount = Decimal(str(discounted_price))
            else:
                discount_amount = Decimal('0')
                final_amount = total_bill
            
        else:
            # Unknown type: no discount
            discount_amount = Decimal('0')
            final_amount = total_bill
        
        # Guard: ensure amounts are never negative
        if discount_amount < Decimal('0'):
            discount_amount = Decimal('0')
        if final_amount < Decimal('0'):
            final_amount = Decimal('0')

        return discount_amount, final_amount
    
    async def _log_analytics_event(self, event_type: str, event_data: Dict):
        """Log analytics event"""
        try:
            self.supabase.table('analytics_events').insert({
                'event_type': event_type,
                'event_data': event_data,
                'created_at': datetime.now(timezone.utc).isoformat()
            }).execute()
        except Exception as e:
            logger.warning(f"Failed to log analytics event: {e}")


# Singleton instance
merchant_service = MerchantService()
