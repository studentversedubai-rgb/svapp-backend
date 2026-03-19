"""
Tickets Router

Public and authenticated endpoints for browsing tickets and managing
ticket booking records.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import get_current_user
from app.modules.tickets.service import TicketService
from app.modules.tickets.schemas import (
    TicketListResponse,
    TicketResponse,
    TicketRecordListResponse,
    TicketRecordResponse,
    UpdateRecordStatusRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ================================
# DEPENDENCY INJECTION
# ================================

def get_ticket_service() -> TicketService:
    """Dependency for ticket service"""
    return TicketService()


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
# GET /tickets  — Public
# ================================

@router.get(
    "",
    response_model=TicketListResponse,
    summary="List active tickets",
    description=(
        "Returns all tickets where is_active=true and today's date falls within "
        "pricing_period_start and pricing_period_end. "
        "Optional case-insensitive filter by merchant_name."
    ),
)
async def list_tickets(
    merchant_name: Optional[str] = Query(
        None,
        description="Case-insensitive filter on merchant name",
    ),
    ticket_service: TicketService = Depends(get_ticket_service),
):
    """
    Public endpoint — no authentication required.
    """
    try:
        return await ticket_service.get_active_tickets(merchant_name=merchant_name)
    except Exception as e:
        logger.error(f"Error in list_tickets: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch tickets",
        )


# ================================
# GET /tickets/records/me  — Auth required
# ================================
# NOTE: This route MUST be declared before /{ticket_id} to avoid
# FastAPI matching "records" as a ticket_id path parameter.

@router.get(
    "/records/me",
    response_model=TicketRecordListResponse,
    summary="Get my ticket records",
    description="Returns all ticket booking records for the authenticated user, ordered by created_at DESC.",
)
async def get_my_ticket_records(
    current_user: dict = Depends(get_current_user),
    ticket_service: TicketService = Depends(get_ticket_service),
):
    """
    Requires JWT authentication.
    User ID is always taken from the validated token, never from the request.
    """
    try:
        user_id = current_user["id"]
        return await ticket_service.get_my_records(user_id=user_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_my_ticket_records: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch ticket records",
        )


# ================================
# GET /tickets/{ticket_id}  — Public
# ================================

@router.get(
    "/{ticket_id}",
    response_model=TicketResponse,
    summary="Get a single ticket",
    description="Returns a single active ticket by ID. Returns 404 if not found or not active.",
)
async def get_ticket(
    ticket_id: UUID,
    ticket_service: TicketService = Depends(get_ticket_service),
):
    """
    Public endpoint — no authentication required.
    """
    try:
        return await ticket_service.get_ticket_by_id(ticket_id=ticket_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_ticket {ticket_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch ticket",
        )


# ================================
# PATCH /tickets/records/{record_id}/status  — Admin only
# ================================

@router.patch(
    "/records/{record_id}/status",
    response_model=TicketRecordResponse,
    summary="Update ticket record status (admin)",
    description=(
        "Admin only. Updates status, e_ticket_url, internal_notes, and/or fulfilled_at "
        "on a ticket_records row. If status='fulfilled' and fulfilled_at is not provided, "
        "it is automatically set to now()."
    ),
)
async def update_ticket_record_status(
    record_id: UUID,
    payload: UpdateRecordStatusRequest,
    current_user: dict = Depends(get_current_user),
    ticket_service: TicketService = Depends(get_ticket_service),
):
    """
    Requires JWT authentication AND admin role.
    """
    _require_admin(current_user)

    try:
        return await ticket_service.update_record_status(
            record_id=record_id,
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
        logger.error(f"Error in update_ticket_record_status {record_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update ticket record",
        )
