"""
Merchant Validation Router

Public endpoints for merchant-side QR validation and redemption.
Does NOT require student JWT authentication.
"""

from fastapi import APIRouter, HTTPException, status, Header
from fastapi.responses import JSONResponse
import logging

from app.modules.merchant.service import merchant_service
from app.modules.merchant.schemas import (
    MerchantValidateRequest,
    MerchantValidateResponse,
    MerchantConfirmRequest,
    MerchantConfirmResponse,
    MerchantVoidRequest,
    MerchantVoidResponse,
    ShiftLoginRequest,
    ShiftLogoutRequest, 
    ShiftLoginResponse
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ================================
# SHIFT SESSIONS
# ================================

@router.post("/shift/login", response_model=ShiftLoginResponse)
async def shift_login(request: ShiftLoginRequest):
    """
    Start merchant shift session with PIN.
    Returns session token valid for 12 hours.
    """
    try:
        result = await merchant_service.shift_login(
            merchant_id=request.merchant_id,
            pin=request.pin
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error in shift login: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Shift login failed. Please try again."
        )


@router.post("/shift/logout")
async def shift_logout(request: ShiftLogoutRequest):
    """
    End merchant shift session by invalidating the token.
    """
    try:
        await merchant_service.shift_logout(request.session_token)
        return {"success": True, "message": "Shift logged out successfully"}
    except Exception as e:
        logger.error(f"Error in shift logout: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Shift logout failed"
        )



# ================================
# VALIDATE QR TOKEN
# ================================

@router.post("/validate", response_model=MerchantValidateResponse)
async def validate_qr_token(request: MerchantValidateRequest, 
x_shift_token: str = Header(..., alias="X-Shift-Token")):
    
    """
    Validate student's QR proof token or backup code.
    Requires active shift session in X-Shift-Token header.
    """

    try:
        code = request.proof_token or request.backup_code
        result = await merchant_service.validate_proof_token(code=code,
                                                            session_token=x_shift_token)
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
async def confirm_redemption(request: MerchantConfirmRequest, 
x_shift_token: str = Header(..., alias="X-Shift-Token")):
    """
    Confirm redemption with bill amount.
    Requires active shift session in X-Shift-Token header.
    """
    try:
        result = await merchant_service.confirm_redemption(
            code=request.proof_token,
            total_bill_amount=request.total_bill_amount,
            session_token=x_shift_token
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
