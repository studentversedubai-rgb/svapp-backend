"""
SV Pay Router

Payment processing module (FEATURE FLAGGED - DISABLED BY DEFAULT)

IMPORTANT: This module is present but disabled via feature flag.
No active payment logic until feature is enabled.

Endpoints (disabled):
- POST /pay/initiate: Initiate payment
- GET /pay/transactions: Get user's transactions
- POST /pay/webhook: Handle payment provider webhooks

NO BUSINESS LOGIC - Structure only
"""

from fastapi import APIRouter, Depends, HTTPException
# from app.core.config import settings
# from app.core.security import get_current_user
# from app.modules.pay.schemas import (
#     InitiatePaymentRequest,
#     PaymentResponse,
#     TransactionList
# )
# from app.modules.pay.service import PaymentService

router = APIRouter()


# Feature flag check - all routes disabled by default
def check_pay_enabled():
    """Dependency to check if SV Pay is enabled"""
    # if not settings.FEATURE_SV_PAY_ENABLED:
    #     raise HTTPException(
    #         status_code=503,
    #         detail="SV Pay is currently disabled"
    #     )
    pass


@router.post("/initiate", dependencies=[Depends(check_pay_enabled)])
async def initiate_payment():
    """
    Initiate payment transaction (DISABLED)
    
    When enabled:
    1. Validate payment amount
    2. Create transaction record
    3. Call PSP/issuer to initiate payment
    4. Return payment URL or token
    
    Returns:
        Payment initiation response
    """
    # TODO: Implement payment initiation
    # TODO: Integrate with PSP (Stripe, etc.)
    pass


@router.get("/transactions", dependencies=[Depends(check_pay_enabled)])
async def get_transactions():
    """
    Get user's payment transactions (DISABLED)
    
    Returns:
        List of user's transactions
    """
    # TODO: Query user transactions
    pass


@router.post("/webhook", dependencies=[Depends(check_pay_enabled)])
async def payment_webhook():
    """
    Handle payment provider webhooks (DISABLED)
    
    Processes:
    - Payment completed
    - Payment failed
    - Refund processed
    
    Returns:
        Webhook acknowledgment
    """
    # TODO: Verify webhook signature
    # TODO: Process payment status update
    # TODO: Update transaction record
    pass
