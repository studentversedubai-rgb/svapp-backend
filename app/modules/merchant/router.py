"""
Merchant Validation Router

Public endpoints for merchant-side QR validation and redemption.
Does NOT require student JWT authentication.
"""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
import logging

from app.modules.merchant.service import merchant_service
from app.modules.merchant.schemas import (
    MerchantValidateRequest,
    MerchantValidateResponse,
    MerchantConfirmRequest,
    MerchantConfirmResponse,
    MerchantVoidRequest,
    MerchantVoidResponse
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ================================
# VALIDATE QR TOKEN
# ================================

@router.post("/validate", response_model=MerchantValidateResponse)
async def validate_qr_token(request: MerchantValidateRequest):
    """
    Validate student's QR proof token
    
    **Public endpoint** - No authentication required
    
    Returns PASS/FAIL with offer details on success.
    
    Business Rules:
    - Token must be valid and not expired (30s TTL)
    - Entitlement must be in ACTIVE state
    - Entitlement must not be expired
    
    Rate Limit: 100 requests per minute per IP
    """
    try:
        result = await merchant_service.validate_proof_token(request.proof_token)
        return result
    except Exception as e:
        logger.error(f"Error in validate endpoint: {e}")
        return MerchantValidateResponse(
            success=False,
            status="FAIL",
            reason="Validation error"
        )


# ================================
# CONFIRM REDEMPTION
# ================================

@router.post("/confirm", response_model=MerchantConfirmResponse)
async def confirm_redemption(request: MerchantConfirmRequest):
    """
    Confirm redemption with merchant PIN and bill amount
    
    **Public endpoint** - No authentication required
    **Requires merchant PIN** for authorization
    
    Calculates discount based on offer type and creates redemption record.
    
    Business Rules:
    - Token must be valid
    - Entitlement must be ACTIVE
    - Merchant PIN must be correct
    - Discount calculated server-side
    - Entitlement marked as USED
    - Token deleted (single-use)
    
    Rate Limit: 60 requests per minute per IP
    """
    try:
        result = await merchant_service.confirm_redemption(
            proof_token=request.proof_token,
            merchant_pin=request.merchant_pin,
            total_bill_amount=request.total_bill_amount
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        import traceback
        logger.error(f"Error in confirm endpoint: {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to confirm redemption. Please try again."
        )


# ================================
# VOID REDEMPTION
# ================================

@router.post("/void", response_model=MerchantVoidResponse)
async def void_redemption(request: MerchantVoidRequest):
    """
    Void a redemption within the void window
    
    **Public endpoint** - No authentication required
    **Requires merchant PIN** for authorization
    
    Voids redemption and restores entitlement if within window.
    
    Business Rules:
    - Must be within 2-hour void window
    - Must be same day as redemption
    - Merchant PIN must be correct
    - Redemption marked as voided
    - Entitlement state updated to VOIDED
    
    Rate Limit: 60 requests per minute per IP
    """
    try:
        result = await merchant_service.void_redemption(
            redemption_id=request.redemption_id,
            merchant_pin=request.merchant_pin,
            reason=request.reason
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error in void endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to void redemption"
        )


# ================================
# HEALTH CHECK
# ================================

@router.get("/health")
async def merchant_health():
    """Health check for merchant endpoints"""
    return {"status": "ok", "service": "merchant-validation"}
