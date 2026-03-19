"""
Payments Router

Mock payment order creation and admin CSV export for ticket bookings.
"""

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from app.core.security import get_current_user
from app.modules.payments.service import PaymentService
from app.modules.payments.schemas import (
    CreateMockOrderRequest,
    CreateMockOrderResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ================================
# DEPENDENCY INJECTION
# ================================

def get_payment_service() -> PaymentService:
    """Dependency for payment service"""
    return PaymentService()


# ================================
# ADMIN GUARD HELPER
# ================================

def _require_admin(current_user: dict) -> None:
    """
    Raise 403 if the authenticated user is not an admin.
    Checks the 'role' field stored in the public.users table.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )


# ================================
# POST /payments/tickets/create-mock-order  — Auth required
# ================================

@router.post(
    "/tickets/create-mock-order",
    response_model=CreateMockOrderResponse,
    summary="Create a mock ticket order (test flow)",
    description=(
        "Validates the ticket, calculates the total, generates a fake payment intent ID, "
        "inserts a ticket_records row already marked as paid, and immediately sends "
        "confirmation emails. No real payment is processed."
    ),
)
async def create_mock_order(
    payload: CreateMockOrderRequest,
    current_user: dict = Depends(get_current_user),
    payment_service: PaymentService = Depends(get_payment_service),
):
    """
    Requires JWT authentication.
    User identity (name, email) is always taken from the validated token,
    never from the request body.
    """
    user_id = current_user["id"]

    # Resolve display name: prefer name, fall back to first_name + last_name
    user_name = (
        current_user.get("name")
        or " ".join(
            filter(None, [current_user.get("first_name"), current_user.get("last_name")])
        )
        or "Student"
    )
    user_email = current_user.get("email", "")

    try:
        return await payment_service.create_mock_order(
            user_id=user_id,
            user_name=user_name,
            user_email=user_email,
            payload=payload,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating mock order: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create mock order",
        )


# ================================
# GET /payments/tickets/records/export  — Admin only
# ================================

@router.get(
    "/tickets/records/export",
    summary="Export ticket records as CSV (admin)",
    description=(
        "Admin only. Returns a downloadable CSV of all ticket_records joined with "
        "ticket info. Optionally filter by created_at date range."
    ),
)
async def export_ticket_records(
    from_date: Optional[date] = Query(
        None,
        description="Filter records created on or after this date (YYYY-MM-DD)",
    ),
    to_date: Optional[date] = Query(
        None,
        description="Filter records created on or before this date (YYYY-MM-DD)",
    ),
    current_user: dict = Depends(get_current_user),
    payment_service: PaymentService = Depends(get_payment_service),
):
    """
    Requires JWT authentication AND admin role.
    Returns Content-Type: text/csv with attachment disposition.
    """
    _require_admin(current_user)

    try:
        csv_content = await payment_service.export_records_csv(
            from_date=from_date.isoformat() if from_date else None,
            to_date=to_date.isoformat() if to_date else None,
        )

        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="ticket_orders_export.csv"'
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting ticket records: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export ticket records",
        )
