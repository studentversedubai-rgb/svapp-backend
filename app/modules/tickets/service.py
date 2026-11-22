"""
Tickets Service

Business logic for fetching tickets and ticket records from PostgreSQL.
"""

import logging
from datetime import date, datetime, timezone
from typing import List, Optional
from uuid import UUID

from app.core.database import fetch_one, fetch_all, execute
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

            sql = """
                SELECT * FROM tickets
                WHERE is_active = true
                  AND pricing_period_start <= %s
                  AND pricing_period_end >= %s
            """
            params = [today, today]

            if merchant_name:
                sql += " AND merchant_name ILIKE %s"
                params.append(f"%{merchant_name}%")

            sql += " ORDER BY created_at DESC"
            rows = fetch_all(sql, tuple(params))

            items = [TicketResponse(**row) for row in rows]
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
            ticket = fetch_one("SELECT * FROM tickets WHERE id = %s", (str(ticket_id),))

            if not ticket:
                raise ValueError("Ticket not found")

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
            sql = """
                SELECT tr.*, t.merchant_name, t.ticket_details
                FROM ticket_records tr
                LEFT JOIN tickets t ON t.id = tr.ticket_id
                WHERE tr.user_id = %s
                ORDER BY tr.created_at DESC
            """
            rows = fetch_all(sql, (user_id,))
            items = [TicketRecordResponse(**row) for row in rows]
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
                if payload.fulfilled_at is not None:
                    update_data["fulfilled_at"] = payload.fulfilled_at.isoformat()
                else:
                    update_data["fulfilled_at"] = datetime.now(timezone.utc).isoformat()
            elif payload.fulfilled_at is not None:
                update_data["fulfilled_at"] = payload.fulfilled_at.isoformat()

            set_clauses = [f"{k} = %s" for k in update_data.keys()]
            params = list(update_data.values()) + [str(record_id)]
            sql = f"UPDATE ticket_records SET {', '.join(set_clauses)} WHERE id = %s"
            rowcount = execute(sql, tuple(params))

            if rowcount == 0:
                raise ValueError("Ticket record not found")

            # Fetch enriched record
            enriched_sql = """
                SELECT tr.*, t.merchant_name, t.ticket_details
                FROM ticket_records tr
                LEFT JOIN tickets t ON t.id = tr.ticket_id
                WHERE tr.id = %s
            """
            row = fetch_one(enriched_sql, (str(record_id),))
            if not row:
                raise ValueError("Ticket record not found")

            return TicketRecordResponse(**row)

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error updating record {record_id}: {e}")
            raise
