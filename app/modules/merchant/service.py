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
import secrets
from typing import Optional, Dict
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import UUID

os.environ.setdefault("PASSLIB_BUILTIN_BCRYPT", "enabled")

from passlib.hash import bcrypt as bcrypt_hasher # pyright: ignore

from app.core.database import get_supabase_client
from app.core.redis import redis_manager
from app.modules.merchant.schemas import (
    MerchantValidateResponse,
    MerchantConfirmResponse,
    MerchantVoidResponse,
    ShiftLoginResponse   
)
from app.shared.enums import EntitlementState
from app.shared.constants import (
    REDIS_PREFIX_QR_TOKEN,
    VOID_WINDOW_HOURS,
    REDIS_PREFIX_BACKUP_CODE,
    REDIS_PREFIX_SHIFT_SESSION,
    SHIFT_SESSION_TTL_SECONDS,
)

logger = logging.getLogger(__name__)


class MerchantService:
    """Handles merchant validation operations"""
    
    def __init__(self):
        """Initialize service"""
        self.supabase = get_supabase_client()
        self.redis = redis_manager

    # ================================
    # SHIFT SESSION MANAGEMENT
    # ================================

    async def shift_login(self, merchant_id: str, pin: str) -> ShiftLoginResponse:
        """
        Authenticate a merchant for a shift and issue a session token.
        """
        merchant = await self._get_merchant(merchant_id)
        if not merchant:
            raise ValueError("Merchant not found")

        # Verify PIN (handles bcrypt & auto-upgrades legacy SHA-256)
        if not await self._verify_merchant_pin(merchant_id, pin):
            raise ValueError("Invalid PIN")

        # Generate secure random token
        session_token = secrets.token_urlsafe(32)

        # Store session in Redis
        redis_key = f"{REDIS_PREFIX_SHIFT_SESSION}{session_token}"
        session_data = json.dumps({"merchant_id": merchant_id})
        self.redis.setex(redis_key, SHIFT_SESSION_TTL_SECONDS, session_data)

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=SHIFT_SESSION_TTL_SECONDS)

        return ShiftLoginResponse(
            success=True,
            session_token=session_token,
            expires_at=expires_at,
            merchant_name=merchant.get("name", "Unknown Merchant")
        )

    async def shift_logout(self, session_token: str) -> None:
        """
        End a merchant shift session by removing the Redis key.
        """
        redis_key = f"{REDIS_PREFIX_SHIFT_SESSION}{session_token}"
        self.redis.delete(redis_key)

    async def _get_session_merchant(self, session_token: str) -> str:
        """
        Validate shift session token and return merchant_id.
        Raises ValueError if session is invalid or expired.
        """
        redis_key = f"{REDIS_PREFIX_SHIFT_SESSION}{session_token}"
        session_data_str = self.redis.get(redis_key)

        if not session_data_str:
            raise ValueError("Shift session expired. Please log in again.")

        session_data = json.loads(session_data_str)
        return session_data["merchant_id"]

    
    # ================================
    # VALIDATE QR TOKEN
    # ================================
    
    async def validate_proof_token(self, code: str, session_token: str) -> MerchantValidateResponse:
        """
        Validate student's QR proof token
        
        Args:
            proof_token: QR proof token from student
            
        Returns:
            Validation response with PASS/FAIL status
        """
        try:
            await self._get_session_merchant(session_token)
            
            if len(code) <= 6:
                # It's definitely a backup code
                redis_key = f"{REDIS_PREFIX_BACKUP_CODE}{code.upper()}"
            else:
                # It's a QR token
                redis_key = f"{REDIS_PREFIX_QR_TOKEN}{code}"

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
                if state_val == EntitlementState.CONFIRMED.value:
                    reason = "This offer has already been redeemed"
                elif state_val == EntitlementState.EXPIRED.value:
                    reason = "Entitlement has expired"
                elif state_val == EntitlementState.CANCELLED.value:
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


            # Mark entitlement as PENDING_CONFIRMATION so concurrent scans are rejected
            self.supabase.table('entitlements').update({
                'state': EntitlementState.PENDING_CONFIRMATION.value,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }).eq('id', str(entitlement_id)).execute()

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

        except ValueError as ve:
            return MerchantValidateResponse(
                success=False,
                status="FAIL",
                reason=str(ve)
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
        code: str,
        total_bill_amount: Decimal,
        session_token: str
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
        session_merchant_id = await self._get_session_merchant(session_token)
        redis_key = f"{REDIS_PREFIX_QR_TOKEN}{code}"
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
            if entitlement['state'] == EntitlementState.CONFIRMED.value:
                raise ValueError("This entitlement has already been redeemed.")
            elif entitlement['state'] == EntitlementState.EXPIRED.value:
                raise ValueError("This entitlement has expired.")
            elif entitlement['state'] == EntitlementState.CANCELLED.value:
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
        
        if str(offer['merchant_id']) != str(session_merchant_id):
            raise ValueError("Offer does not belong to your merchant account")

        
        # Calculate discount and final amount
        discount_amount, final_amount = self._calculate_savings(
            offer['offer_type'],
            total_bill_amount,
            offer.get('discount_value'),
            offer.get('original_price'),
            offer.get('discounted_price')
        )

        # Determine commission tier for April 2027 billing
        discount_value_str = str(offer.get('discount_value') or '')
        match = re.search(r"\d+(?:\.\d+)?", discount_value_str)
        discount_pct = float(match.group(0)) if match else 0.0

        if discount_pct >= 25:
            commission_tier = 25
        elif discount_pct >= 20:
            commission_tier = 20
        else:
            commission_tier = 15
        

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
            'commission_tier': commission_tier,
            'redeemed_at': datetime.now(timezone.utc).isoformat(),
            'is_voided': False
        }
        
        result = self.supabase.table('redemptions').insert(redemption_data).execute()
        
        if not result.data:
            raise ValueError("Failed to create redemption")
        
        redemption = result.data[0]
        
        # Mark entitlement as CONFIRMED
        self.supabase.table('entitlements').update({
            'state': EntitlementState.CONFIRMED.value,
            'used_at': datetime.now(timezone.utc).isoformat()
        }).eq('id', str(entitlement_id)).execute()
        
        # Delete BOTH QR token and backup code from Redis
        proof_tok = token_data.get('proof_token') or (code if len(code) > 6 else None)
        backup_c = token_data.get('backup_code') or (code if len(code) <= 6 else None)
        if proof_tok:
            self.redis.delete(f"{REDIS_PREFIX_QR_TOKEN}{proof_tok}")
        if backup_c:
            self.redis.delete(f"{REDIS_PREFIX_BACKUP_CODE}{backup_c.upper()}")
        
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
            'state': EntitlementState.CANCELLED.value,
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
        Verify merchant PIN with automatic upgrade from SHA-256 to bcrypt.
        """
        merchant = await self._get_merchant(merchant_id)
        if not merchant:
            return False

        stored_hash = merchant.get('pin_hash')
        if not stored_hash:
            logger.warning(f"No PIN hash for merchant {merchant_id}")
            return False

        # CASE 1: Already bcrypt (modern, secure)
        if stored_hash.startswith('$2a$') or stored_hash.startswith('$2b$') or stored_hash.startswith('$2y$'):
            return bcrypt_hasher.verify(pin, stored_hash)

        # CASE 2: Old SHA-256 hash (legacy, needs upgrade)
        if re.fullmatch(r"[0-9a-fA-F]{64}", stored_hash):
            # Verify with SHA-256
            pin_hash = hashlib.sha256(pin.encode('utf-8')).hexdigest()
            if hmac.compare_digest(pin_hash, stored_hash.lower()):
                # PIN is correct - AUTOMATICALLY UPGRADE to bcrypt
                new_hash = bcrypt_hasher.hash(pin)
                await self._upgrade_merchant_pin_hash(merchant_id, new_hash)
                logger.info(f"Auto-upgraded PIN hash for merchant {merchant_id} from SHA-256 to bcrypt")
                return True
            return False

        # CASE 3: Unknown format - reject
        logger.warning(f"Unknown PIN hash format for merchant {merchant_id}")
        return False


    async def _upgrade_merchant_pin_hash(self, merchant_id: str, new_hash: str) -> None:
        """Upgrade merchant's PIN hash to bcrypt."""
        try:
            self.supabase.table("merchants").update({
                "pin_hash": new_hash
            }).eq("id", merchant_id).execute()
        except Exception as e:
            logger.error(f"Failed to upgrade PIN hash for merchant {merchant_id}: {e}")   

    
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
