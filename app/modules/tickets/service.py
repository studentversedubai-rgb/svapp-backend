"""
Tickets Service

Business logic for fetching tickets and ticket records from Supabase.
"""

import logging
from datetime import date, datetime, timezone
from typing import List, Optional
from uuid import UUID

from app.core.database import get_supabase_client
from app.modules.tickets.schemas import (
    TicketResponse,
    TicketListResponse,
    TicketRecordResponse,
    TicketRecordListResponse,
    UpdateRecordStatusRequest,
)

logger = logging.getLogger(__name__)


class TicketService:
    """Handles ticket browse and record retrieval operations"""

    def __init__(self):
        self.supabase = get_supabase_client()

    # ================================
    # PUBLIC: LIST TICKETS
    # ================================

    async def get_active_tickets(
        self,
        merchant_name: Optional[str] = None,
    ) -> TicketListResponse:
        """
        Return all active tickets whose pricing period covers today.

        Args:
            merchant_name: Optional case-insensitive filter on merchant_name.

        Returns:
            TicketListResponse
        """
        try:
            today = date.today().isoformat()

            query = (
                self.supabase.table("tickets")
                .select("*")
                .eq("is_active", True)
                .lte("pricing_period_start", today)
                .gte("pricing_period_end", today)
            )

            if merchant_name:
                # Escape LIKE wildcard special characters (\, %, _)
                safe_name = (
                    merchant_name
                    .replace("\\", "\\\\")
                    .replace("%", "\\%")
                    .replace("_", "\\_")
                )
                query = query.ilike("merchant_name", f"%{safe_name}%")

            result = query.execute()

            items = [TicketResponse(**row) for row in (result.data or [])]
            return TicketListResponse(items=items, total=len(items))

        except Exception as e:
            logger.error(f"Error fetching active tickets: {e}")
            raise

    # ================================
    # PUBLIC: GET SINGLE TICKET
    # ================================

    async def get_ticket_by_id(self, ticket_id: UUID) -> TicketResponse:
        """
        Return a single active ticket by ID.

        Args:
            ticket_id: UUID of the ticket.

        Returns:
            TicketResponse

        Raises:
            ValueError: If ticket not found or not active.
        """
        try:
            result = (
                self.supabase.table("tickets")
                .select("*")
                .eq("id", str(ticket_id))
                .execute()
            )

            if not result.data:
                raise ValueError("Ticket not found")

            ticket = result.data[0]

            if not ticket.get("is_active", False):
                raise ValueError("Ticket is not currently available")

            return TicketResponse(**ticket)

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error fetching ticket {ticket_id}: {e}")
            raise

    # ================================
    # AUTH: USER'S TICKET RECORDS
    # ================================

    async def get_my_records(self, user_id: str) -> TicketRecordListResponse:
        """
        Return all ticket_records for the authenticated user, joined with ticket info.

        Args:
            user_id: Authenticated user ID from JWT.

        Returns:
            TicketRecordListResponse
        """
        try:
            result = (
                self.supabase.table("ticket_records")
                .select("*, ticket:tickets(merchant_name, ticket_details)")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .execute()
            )

            items = []
            for row in (result.data or []):
                # Flatten joined ticket fields onto the record dict
                ticket_join = row.pop("ticket", None) or {}
                if isinstance(ticket_join, list):
                    ticket_join = ticket_join[0] if ticket_join else {}
                row["merchant_name"] = ticket_join.get("merchant_name")
                row["ticket_details"] = ticket_join.get("ticket_details")
                items.append(TicketRecordResponse(**row))

            return TicketRecordListResponse(items=items, total=len(items))

        except Exception as e:
            logger.error(f"Error fetching records for user {user_id}: {e}")
            raise

    # ================================
    # ADMIN: UPDATE RECORD STATUS
    # ================================

    async def update_record_status(
        self,
        record_id: UUID,
        payload: UpdateRecordStatusRequest,
    ) -> TicketRecordResponse:
        """
        Admin: update status (and optional fields) on a ticket_records row.

        If status is 'fulfilled' and fulfilled_at is not provided, it is
        automatically set to the current UTC timestamp.

        Args:
            record_id: UUID of the ticket_records row.
            payload: Fields to update.

        Returns:
            Updated TicketRecordResponse.

        Raises:
            ValueError: If record not found.
        """
        try:
            update_data: dict = {"status": payload.status}

            if payload.e_ticket_url is not None:
                update_data["e_ticket_url"] = payload.e_ticket_url

            if payload.internal_notes is not None:
                update_data["internal_notes"] = payload.internal_notes

            if payload.status == "fulfilled":
                # Auto-set fulfilled_at to now() if caller didn't provide it
                if payload.fulfilled_at is not None:
                    update_data["fulfilled_at"] = payload.fulfilled_at.isoformat()
                else:
                    update_data["fulfilled_at"] = datetime.now(timezone.utc).isoformat()
            elif payload.fulfilled_at is not None:
                update_data["fulfilled_at"] = payload.fulfilled_at.isoformat()

            result = (
                self.supabase.table("ticket_records")
                .update(update_data)
                .eq("id", str(record_id))
                .execute()
            )

            if not result.data:
                raise ValueError("Ticket record not found")

            row = result.data[0]

            # Fetch joined ticket info to enrich response
            ticket_result = (
                self.supabase.table("tickets")
                .select("merchant_name, ticket_details")
                .eq("id", str(row["ticket_id"]))
                .execute()
            )
            ticket_info = ticket_result.data[0] if ticket_result.data else {}
            row["merchant_name"] = ticket_info.get("merchant_name")
            row["ticket_details"] = ticket_info.get("ticket_details")

            return TicketRecordResponse(**row)

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error updating record {record_id}: {e}")
            raise
