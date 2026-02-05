"""
Entitlements Router - Phase 3

CORE MODULE: QR-based redemption system with merchant validation.

Endpoints:
- POST /entitlements/claim: Claim an offer
- POST /entitlements/{id}/proof: Generate QR proof token
- POST /entitlements/validate: Validate proof token (merchant)
- POST /entitlements/confirm: Confirm redemption with amount
- POST /entitlements/void: Void a redemption
- GET /entitlements/my: Get user's entitlements
- GET /entitlements/{id}: Get entitlement details
- GET /entitlements/savings: Get user's savings summary

ALL ENDPOINTS REQUIRE AUTHENTICATION
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional, Dict
from app.core.security import get_current_user
from app.modules.entitlements.service import entitlement_service
from app.modules.entitlements.schemas import (
    ClaimEntitlementRequest,
    ClaimEntitlementResponse,
    GenerateProofResponse,
    ValidateTokenRequest,
    ValidateTokenResponse,
    ConfirmRedemptionRequest,
    ConfirmRedemptionResponse,
    VoidRedemptionRequest,
    VoidRedemptionResponse,
    EntitlementListItem,
    EntitlementDetail,
    UserSavingsSummary
)

router = APIRouter()


# ================================
# CLAIM ENTITLEMENT
# ================================

@router.post("/claim", response_model=ClaimEntitlementResponse)
async def claim_entitlement(
    request: ClaimEntitlementRequest,
    current_user: Dict = Depends(get_current_user)
):
    """
    Claim an offer to create an entitlement
    
    Business Rules:
    - One entitlement per user per offer per day
    - Offer must be active and valid
    - Entitlement expires at end of day
    
    Returns:
        Created entitlement with ID and expiry
    """
    try:
        user_id = current_user['id']
        
        result = await entitlement_service.claim_entitlement(
            user_id=user_id,
            offer_id=request.offer_id,
            device_id=request.device_id
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"Error claiming entitlement: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to claim entitlement: {str(e)}"
        )



# ================================
# QR PROOF TOKEN GENERATION
# ================================

@router.post("/{entitlement_id}/proof", response_model=GenerateProofResponse)
async def generate_proof_token(
    entitlement_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """
    Generate short-lived proof token for QR code
    
    Token Details:
    - TTL: 30 seconds
    - Single-use
    - Stored in Redis
    - Frontend renders QR code from token
    
    Returns:
        Proof token and expiry timestamp
    """
    try:
        user_id = current_user['id']
        
        result = await entitlement_service.generate_proof_token(
            entitlement_id=entitlement_id,
            user_id=user_id
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate proof token"
        )


# ================================
# VALIDATION (MERCHANT SIDE)
# ================================

@router.post("/validate", response_model=ValidateTokenResponse)
async def validate_proof_token(
    request: ValidateTokenRequest,
    current_user: Dict = Depends(get_current_user)
):
    """
    Validate proof token (merchant scans QR)
    
    Validation Checks:
    - Token exists in Redis
    - Entitlement is active
    - Not already used
    - Device binding
    - Time window
    
    On Success:
    - Marks entitlement as PENDING_CONFIRMATION
    - Returns offer details for merchant
    
    Returns:
        PASS/FAIL with offer details
    """
    try:
        result = await entitlement_service.validate_proof_token(
            proof_token=request.proof_token
        )
        
        return result
        
    except Exception as e:
        # Don't expose internal errors to merchant
        return ValidateTokenResponse(
            success=False,
            status="FAIL",
            reason="Validation failed"
        )


# ================================
# AMOUNT CAPTURE & CONFIRMATION
# ================================

@router.post("/confirm", response_model=ConfirmRedemptionResponse)
async def confirm_redemption(
    request: ConfirmRedemptionRequest,
    current_user: Dict = Depends(get_current_user)
):
    """
    Confirm redemption with amount capture
    
    Merchant Flow:
    1. Scan QR (validate endpoint)
    2. Enter bill amount
    3. Confirm redemption (this endpoint)
    
    Savings Calculation:
    - Percentage: total * (percentage / 100)
    - BOGO: item price
    - Bundle: original_price - bundle_price
    
    On Success:
    - Creates redemption record
    - Marks entitlement as USED
    - Deletes Redis token
    - Sends notification to student
    
    Returns:
        Redemption confirmation with savings breakdown
    """
    try:
        result = await entitlement_service.confirm_redemption(
            entitlement_id=request.entitlement_id,
            total_bill_amount=request.total_bill_amount,
            discounted_amount=request.discounted_amount
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to confirm redemption"
        )


# ================================
# VOID LOGIC
# ================================

@router.post("/void", response_model=VoidRedemptionResponse)
async def void_redemption(
    request: VoidRedemptionRequest,
    current_user: Dict = Depends(get_current_user)
):
    """
    Void a redemption within 2-hour window
    
    Business Rules:
    - Only USED entitlements can be voided
    - Must be within 2 hours of redemption
    - Same day only
    - Requires reason (audit log)
    
    On Success:
    - Marks redemption as voided
    - Marks entitlement as VOIDED
    
    Returns:
        Void confirmation
    """
    try:
        # Optional: Check if user is admin/merchant
        # For now, allow any authenticated user
        
        result = await entitlement_service.void_redemption(
            entitlement_id=request.entitlement_id,
            reason=request.reason,
            user_id=current_user['id']
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to void redemption"
        )


# ================================
# QUERY ENDPOINTS
# ================================

@router.get("/my", response_model=list[EntitlementListItem])
async def get_my_entitlements(
    state: Optional[str] = None,
    current_user: Dict = Depends(get_current_user)
):
    """
    Get current user's entitlements
    
    Query Params:
    - state: Filter by state (active, used, voided, expired)
    
    Returns:
        List of user's entitlements
    """
    try:
        user_id = current_user['id']
        
        entitlements = await entitlement_service.get_user_entitlements(
            user_id=user_id,
            state_filter=state
        )
        
        return entitlements
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch entitlements"
        )


@router.get("/savings", response_model=UserSavingsSummary)
async def get_user_savings(
    current_user: Dict = Depends(get_current_user)
):
    """
    Get user's total savings summary
    
    Returns:
        Total redemptions, savings, and spending
    """
    try:
        user_id = current_user['id']
        
        summary = await entitlement_service.get_user_savings_summary(user_id)
        
        return summary
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch savings summary"
        )


# ================================
# ADMIN/ANALYTICS ENDPOINTS (Future)
# ================================

# TODO: Add admin endpoints for:
# - Merchant redemption stats
# - Offer redemption stats
# - Revenue analytics
# - Fraud detection reports
