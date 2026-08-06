"""
Payments Service

Mock payment flow for ticket bookings (no real Stripe integration).
Sends confirmation emails via existing Postmark setup and provides
admin CSV export.
"""

import csv
import io
import logging
import os
import uuid as uuid_lib
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from postmarker.core import PostmarkClient

from app.core.database import get_supabase_client
from app.core.activity import log_activity_event
from app.modules.payments.schemas import (
    CreateMockOrderRequest,
    CreateMockOrderResponse,
    CreatePaymentIntentRequest,
    CreatePaymentIntentResponse,
    ConfirmPaymentRequest,
    ConfirmPaymentResponse,
)

logger = logging.getLogger(__name__)

# ================================
# EMAIL CONFIGURATION
# ================================

POSTMARK_API_KEY = os.getenv("POSTMARK_API_KEY", "")
FROM_ADDRESS = "support@studentverse.app"
INTERNAL_BOOKINGS_EMAIL = os.getenv("INTERNAL_BOOKINGS_EMAIL", "")


class PaymentService:
    """Handles mock payment order creation, email notifications, and CSV export"""

    def __init__(self):
        self.supabase = get_supabase_client()

    # ================================
    # CREATE MOCK ORDER
    # ================================

    async def create_mock_order(
        self,
        user_id: str,
        user_name: str,
        user_email: str,
        payload: CreateMockOrderRequest,
    ) -> CreateMockOrderResponse:
        """
        Create a mock ticket order — simulates instant payment without Stripe.

        Steps:
        1. Validate the ticket (must be active and within pricing period)
        2. Calculate total_price
        3. Generate a fake mock_pi_ payment intent ID
        4. Insert ticket_records row with stripe_payment_status='paid', status='paid'
        5. Send confirmation emails (failures are logged, never crash the response)

        Args:
            user_id:    Authenticated user ID (from JWT).
            user_name:  User's display name (from public.users).
            user_email: User's email address (from public.users / auth).
            payload:    Validated request body.

        Returns:
            CreateMockOrderResponse

        Raises:
            ValueError: If ticket not found, not active, or outside pricing period.
            Exception:  On database errors.
        """
        # 1. Fetch and validate the ticket
        ticket = await self._get_active_ticket(payload.ticket_id)

        merchant_name = ticket.get("merchant_name", "Unknown Merchant")
        ticket_details = ticket.get("ticket_details", "")

        # 2. Calculate total
        our_price = float(ticket["our_price"])
        total_price = round(our_price * payload.quantity, 2)

        # 3. Generate fake payment intent ID
        mock_payment_intent_id = f"mock_pi_{uuid_lib.uuid4().hex}"

        # 4. Insert ticket_records row — already marked as paid
        record_data = {
            "ticket_id": str(payload.ticket_id),
            "user_id": user_id,
            "contact_name": user_name,
            "contact_email": payload.contact_email,
            "contact_phone": payload.contact_phone,
            "visit_date": payload.visit_date.isoformat() if payload.visit_date else None,
            "visit_time": str(payload.visit_time) if payload.visit_time else None,
            "quantity": payload.quantity,
            "special_requests": payload.special_requests,
            "unit_price": our_price,
            "total_price": total_price,
            "stripe_payment_intent_id": mock_payment_intent_id,
            "stripe_payment_status": "paid",
            "status": "paid",
        }

        insert_result = (
            self.supabase.table("ticket_records").insert(record_data).execute()
        )

        if not insert_result.data:
            raise Exception("Failed to create ticket record in database")

        record = insert_result.data[0]

        # 5. Send emails — failures are logged but never crash the response
        # (record is already saved at this point)
        try:
            self._send_confirmation_email_to_user(record, merchant_name, ticket_details)
        except Exception as e:
            logger.error(f"Failed to send user confirmation email: {e}", exc_info=True)


        return CreateMockOrderResponse(
            record_id=UUID(record["id"]),
            mock_payment_intent_id=mock_payment_intent_id,
            total_price=total_price,
            status="paid",
            message="Mock payment successful. This is a test flow — no real payment was processed.",
        )

    # ================================
    # ADMIN CSV EXPORT
    # ================================

    async def export_records_csv(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> str:
        """
        Admin: export all ticket_records (joined with tickets) as CSV.

        Args:
            from_date: Optional ISO date string (YYYY-MM-DD) — filter by created_at >=.
            to_date:   Optional ISO date string (YYYY-MM-DD) — filter by created_at <=.

        Returns:
            CSV string ready to stream.
        """
        query = (
            self.supabase.table("ticket_records")
            .select("*, ticket:tickets(merchant_name, ticket_details)")
            .order("created_at", desc=True)
        )

        if from_date:
            query = query.gte("created_at", f"{from_date}T00:00:00+00:00")
        if to_date:
            query = query.lte("created_at", f"{to_date}T23:59:59+00:00")

        result = query.execute()
        rows = result.data or []

        # Flatten joined ticket data
        for row in rows:
            ticket_join = row.pop("ticket", None) or {}
            if isinstance(ticket_join, list):
                ticket_join = ticket_join[0] if ticket_join else {}
            row["merchant_name"] = ticket_join.get("merchant_name", "")
            row["ticket_type"] = ticket_join.get("ticket_details", "")

        # Build CSV
        columns = [
            "order_id",
            "booked_at",
            "merchant_name",
            "ticket_type",
            "contact_name",
            "contact_email",
            "contact_phone",
            "visit_date",
            "visit_time",
            "quantity",
            "unit_price",
            "total_price",
            "stripe_payment_status",
            "order_status",
            "special_requests",
            "e_ticket_url",
            "fulfilled_at",
            "internal_notes",
        ]

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()

        for row in rows:
            writer.writerow(
                {
                    "order_id": row.get("id", ""),
                    "booked_at": row.get("created_at", ""),
                    "merchant_name": row.get("merchant_name", ""),
                    "ticket_type": row.get("ticket_type", ""),
                    "contact_name": row.get("contact_name", ""),
                    "contact_email": row.get("contact_email", ""),
                    "contact_phone": row.get("contact_phone", ""),
                    "visit_date": row.get("visit_date", ""),
                    "visit_time": row.get("visit_time", ""),
                    "quantity": row.get("quantity", ""),
                    "unit_price": row.get("unit_price", ""),
                    "total_price": row.get("total_price", ""),
                    "stripe_payment_status": row.get("stripe_payment_status", ""),
                    "order_status": row.get("status", ""),
                    "special_requests": row.get("special_requests", ""),
                    "e_ticket_url": row.get("e_ticket_url", ""),
                    "fulfilled_at": row.get("fulfilled_at", ""),
                    "internal_notes": row.get("internal_notes", ""),
                }
            )

        return output.getvalue()

    # ================================
    # PRIVATE HELPERS
    # ================================

    async def _get_active_ticket(self, ticket_id: UUID) -> dict:
        """
        Fetch an active ticket whose pricing period covers today.

        Raises:
            ValueError: If ticket not found, not active, or outside pricing period.
        """
        from datetime import date

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
            raise ValueError("Ticket is not currently active")

        today = date.today()

        def _parse_date(val):
            if val is None:
                return None
            if isinstance(val, date):
                return val
            return date.fromisoformat(str(val)[:10])

        period_start = _parse_date(ticket.get("pricing_period_start"))
        period_end = _parse_date(ticket.get("pricing_period_end"))

        if period_start and today < period_start:
            raise ValueError("Ticket pricing period has not started yet")
        if period_end and today > period_end:
            raise ValueError("Ticket pricing period has ended")

        return ticket

    def _send_confirmation_email_to_user(
        self, record: dict, merchant_name: str, ticket_details: str
    ) -> None:
        """Send booking confirmation email to the customer via Postmark."""
        if not POSTMARK_API_KEY:
            logger.error("Cannot send email: POSTMARK_API_KEY not configured")
            raise Exception("Email service not configured: POSTMARK_API_KEY missing")

        visit_date = record.get("visit_date") or "Open Dated"
        visit_time = record.get("visit_time") or "Not specified"
        quantity = record.get("quantity", 1)
        total_price = record.get("total_price", 0)
        contact_email = record.get("contact_email", "")
        contact_name = record.get("contact_name", "")
        order_id = record.get("id", "")

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Booking Confirmed</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: #000000;
            color: #ffffff;
            line-height: 1.6;
            padding: 20px;
        }}
        .container {{
            max-width: 480px;
            margin: 0 auto;
            background-color: rgba(18, 18, 18, 0.6);
            border-radius: 20px;
            overflow: hidden;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        .header {{
            background: linear-gradient(90deg, #FF6B35 0%, #F72585 50%, #7209B7 100%);
            padding: 32px 24px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 28px;
            font-weight: 800;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 2px;
        }}
        .header .subtitle {{
            font-size: 14px;
            opacity: 0.9;
            font-weight: 500;
        }}
        .content {{
            padding: 28px 24px;
        }}
        .greeting {{
            margin-bottom: 24px;
        }}
        .greeting p {{
            font-size: 16px;
            color: #ffffff;
            margin-bottom: 8px;
        }}
        .greeting p:first-child {{
            font-size: 20px;
            font-weight: 700;
            color: #9C27B0;
        }}
        .details-card {{
            background-color: #121212;
            border-radius: 16px;
            padding: 24px;
            margin: 24px 0;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        .details-card h2 {{
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            color: #9C27B0;
            margin-bottom: 20px;
            font-weight: 700;
        }}
        .detail-row {{
            display: flex;
            justify-content: space-between;
            padding: 12px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }}
        .detail-row:last-child {{
            border-bottom: none;
        }}
        .detail-label {{
            color: #888888;
            font-size: 14px;
            font-weight: 500;
        }}
        .detail-value {{
            color: #ffffff;
            font-size: 14px;
            font-weight: 600;
            text-align: right;
        }}
        .total-row {{
            background: linear-gradient(90deg, #FF6B35 0%, #F72585 50%, #7209B7 100%);
            margin: 24px -24px -28px;
            padding: 24px;
            text-align: center;
        }}
        .total-row .detail-label {{
            color: rgba(255,255,255,0.8);
            font-size: 14px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1.5px;
        }}
        .total-row .detail-value {{
            color: #ffffff;
            font-size: 32px;
            font-weight: 800;
            margin-top: 8px;
        }}
        .footer {{
            background-color: #000000;
            padding: 24px;
            text-align: center;
            border-top: 1px solid rgba(255, 255, 255, 0.08);
        }}
        .footer p {{
            color: #888888;
            font-size: 13px;
            margin-bottom: 6px;
            line-height: 1.5;
        }}
        .footer .brand {{
            background: linear-gradient(90deg, #FF6B35 0%, #F72585 50%, #7209B7 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            font-weight: 700;
            font-size: 16px;
            margin-top: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        @media (max-width: 480px) {{
            body {{
                padding: 12px;
            }}
            .container {{
                border-radius: 16px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Booking Confirmed!</h1>
            <p class="subtitle">Your order has been successfully placed</p>
        </div>
        
        <div class="content">
            <div class="greeting">
                <p>Hi {contact_name},</p>
                <p>Your StudentVerse booking is confirmed. Check out your booking details below:</p>
            </div>
            
            <div class="details-card">
                <h2>Booking Details</h2>
                <div class="detail-row">
                    <span class="detail-label">Merchant</span>
                    <span class="detail-value">{merchant_name}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Ticket Type</span>
                    <span class="detail-value">{ticket_details}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Visit Date</span>
                    <span class="detail-value">{visit_date}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Visit Time</span>
                    <span class="detail-value">{visit_time}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Quantity</span>
                    <span class="detail-value">{quantity}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Order ID</span>
                    <span class="detail-value" style="font-size: 11px; word-break: break-all;">{order_id}</span>
                </div>
            </div>
            
            <div class="total-row">
                <div class="detail-label">Total Paid</div>
                <div class="detail-value">AED {total_price}</div>
            </div>
        </div>
        
        <div class="footer">
            <p>Your e-ticket(s) will be delivered to this email within 24 hours.</p>
            <p>If you have any questions, reply to this email.</p>
            <p class="brand">StudentVerse</p>
        </div>
    </div>
</body>
</html>"""

        plain_text = f"""Hi {contact_name},

Your StudentVerse booking is confirmed! 🎉

Here are your booking details:

  Merchant:      {merchant_name}
  Ticket Type:   {ticket_details}
  Visit Date:    {visit_date}
  Visit Time:    {visit_time}
  Quantity:      {quantity}
  Total Paid:    AED {total_price}
  Order ID:      {order_id}

Your e-ticket(s) will be delivered to this email within 24 hours.

If you have any questions, please reply to this email.

Thank you for choosing StudentVerse!

---
StudentVerse Team"""

        client = PostmarkClient(server_token=POSTMARK_API_KEY)
        result = client.emails.send(
            From=FROM_ADDRESS,
            To=contact_email,
            Subject="Your StudentVerse booking is confirmed 🎉",
            HtmlBody=html_content,
            TextBody=plain_text,
        )

        error_code = result.get("ErrorCode", -1) if isinstance(result, dict) else -1
        if error_code != 0:
            raise Exception(f"Postmark send failed (user email): {result}")

        logger.info(
            f"Confirmation email sent to {contact_email}. "
            f"Postmark MessageID: {result.get('MessageID')}"
        )


    # ================================
    # STRIPE INTEGRATION
    # ================================

    async def create_payment_intent(
        self,
        user_id: str,
        user_name: str,
        user_email: str,
        payload: "CreatePaymentIntentRequest",
    ) -> "CreatePaymentIntentResponse":
        import stripe
        from app.core.config import Settings
        from fastapi import HTTPException
        
        settings = Settings()
        stripe.api_key = settings.STRIPE_SECRET_KEY
        
        if not stripe.api_key:
            raise HTTPException(500, "Stripe is not configured")
        
        ticket = await self._get_active_ticket(payload.ticket_id)
        amount_in_fils = int(float(ticket["our_price"]) * payload.quantity * 100)
        
        # Get or create customer
        user_result = self.supabase.table("users").select("stripe_customer_id").eq("id", user_id).execute()
        if not user_result.data:
            raise ValueError("User not found")
            
        stripe_customer_id = user_result.data[0].get("stripe_customer_id")
        
        if stripe_customer_id:
            try:
                customer = stripe.Customer.retrieve(stripe_customer_id)
            except Exception:
                customer = stripe.Customer.create(email=user_email, metadata={"user_id": str(user_id)})
                self.supabase.table("users").update({"stripe_customer_id": customer.id}).eq("id", user_id).execute()
        else:
            customer = stripe.Customer.create(email=user_email, metadata={"user_id": str(user_id)})
            self.supabase.table("users").update({"stripe_customer_id": customer.id}).eq("id", user_id).execute()
            
        ephemeral_key = stripe.EphemeralKey.create(
            customer=customer.id,
            stripe_version="2024-06-20"
        )
        
        visit_date_str = payload.visit_date.isoformat() if payload.visit_date else ""
        
        payment_intent = stripe.PaymentIntent.create(
            amount=amount_in_fils,
            currency="aed",
            customer=customer.id,
            metadata={
                "ticket_id": str(payload.ticket_id),
                "quantity": str(payload.quantity),
                "visit_date": visit_date_str,
                "user_id": str(user_id),
            }
        )
        
        record_data = {
            "ticket_id": str(payload.ticket_id),
            "user_id": user_id,
            "contact_name": user_name,
            "contact_email": payload.contact_email,
            "contact_phone": payload.contact_phone,
            "visit_date": visit_date_str or None,
            "visit_time": str(payload.visit_time) if payload.visit_time else None,
            "quantity": payload.quantity,
            "special_requests": payload.special_requests,
            "unit_price": float(ticket["our_price"]),
            "total_price": float(ticket["our_price"]) * payload.quantity,
            "stripe_customer_id": customer.id,
            "stripe_payment_intent_id": payment_intent.id,
            "payment_status": "pending",
        }
        
        insert_result = self.supabase.table("ticket_records").insert(record_data).execute()
        record = insert_result.data[0]
        
        stripe.PaymentIntent.modify(
            payment_intent.id,
            metadata={**payment_intent.metadata.to_dict(), "record_id": str(record["id"])}
        )
        
        from app.modules.payments.schemas import CreatePaymentIntentResponse
        return CreatePaymentIntentResponse(
            payment_intent_client_secret=payment_intent.client_secret,
            ephemeral_key_secret=ephemeral_key.secret,
            customer_id=customer.id,
            record_id=UUID(record["id"]),
            total_price=float(ticket["our_price"]) * payload.quantity,
            currency="aed"
        )

    async def confirm_payment(
        self,
        user_id: str,
        payload: "ConfirmPaymentRequest",
    ) -> "ConfirmPaymentResponse":
        import stripe
        from app.core.config import Settings
        from fastapi import HTTPException
        
        settings = Settings()
        stripe.api_key = settings.STRIPE_SECRET_KEY
        
        record_result = self.supabase.table("ticket_records").select("*, ticket:tickets(merchant_name, ticket_details)").eq("id", str(payload.record_id)).execute()
        if not record_result.data:
            raise HTTPException(404, "Record not found")
            
        record = record_result.data[0]
        if record["user_id"] != user_id:
            raise HTTPException(400, "Record does not belong to user")
            
        if record.get("payment_status") == "confirmed":
            from app.modules.payments.schemas import ConfirmPaymentResponse
            return ConfirmPaymentResponse(
                record_id=payload.record_id,
                status="confirmed",
                message="Booking confirmed successfully"
            )
            
        payment_intent = stripe.PaymentIntent.retrieve(payload.payment_intent_id)
        if payment_intent.status != "succeeded":
            raise HTTPException(400, "Payment has not succeeded")
            
        if payment_intent.metadata.to_dict().get("record_id") != str(payload.record_id):
            raise HTTPException(400, "PaymentIntent does not match this booking")
            
        self.supabase.table("ticket_records").update({"payment_status": "confirmed"}).eq("id", str(payload.record_id)).execute()

        ticket_join = record.get("ticket", {})
        if isinstance(ticket_join, list):
            ticket_join = ticket_join[0] if ticket_join else {}
        merchant_name = ticket_join.get("merchant_name", "Unknown Merchant")
        ticket_details = ticket_join.get("ticket_details", "")

        # Realtime user activity feed
        log_activity_event(
            user_id,
            "ticket_purchase",
            event_data={
                "record_id": str(payload.record_id),
                "ticket_id": record.get("ticket_id"),
                "ticket_name": ticket_details,
                "merchant_name": merchant_name,
                "total_price": record.get("total_price"),
                "quantity": record.get("quantity"),
            },
        )

        try:
            self._send_confirmation_email_to_user(record, merchant_name, ticket_details)
        except Exception as e:
            logger.error(f"Email failed: {e}")
            
        from app.modules.payments.schemas import ConfirmPaymentResponse
        return ConfirmPaymentResponse(
            record_id=payload.record_id,
            status="confirmed",
            message="Booking confirmed successfully"
        )

    async def handle_webhook(self, payload: bytes, sig_header: str):
        import stripe
        from app.core.config import Settings
        from fastapi import HTTPException
        
        settings = Settings()
        if not settings.STRIPE_WEBHOOK_SECRET:
            raise HTTPException(500, "Stripe webhook secret not configured")
        
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except stripe.error.SignatureVerificationError:
            raise HTTPException(400, "Invalid signature")
            
        if event["type"] == "payment_intent.succeeded":
            payment_intent = event["data"]["object"]
            record_id = payment_intent.get("metadata", {}).get("record_id")
            
            if record_id:
                record_result = self.supabase.table("ticket_records").select("*, ticket:tickets(merchant_name, ticket_details)").eq("id", record_id).execute()
                if record_result.data:
                    record = record_result.data[0]
                    if record.get("payment_status") != "confirmed":
                        self.supabase.table("ticket_records").update({"payment_status": "confirmed"}).eq("id", record_id).execute()

                        ticket_join = record.get("ticket", {})
                        if isinstance(ticket_join, list):
                            ticket_join = ticket_join[0] if ticket_join else {}
                        merchant_name = ticket_join.get("merchant_name", "Unknown Merchant")
                        ticket_details = ticket_join.get("ticket_details", "")

                        # Realtime user activity feed
                        if record.get("user_id"):
                            log_activity_event(
                                record["user_id"],
                                "ticket_purchase",
                                event_data={
                                    "record_id": record_id,
                                    "ticket_id": record.get("ticket_id"),
                                    "ticket_name": ticket_details,
                                    "merchant_name": merchant_name,
                                    "total_price": record.get("total_price"),
                                    "quantity": record.get("quantity"),
                                },
                            )

                        try:
                            self._send_confirmation_email_to_user(record, merchant_name, ticket_details)
                        except Exception as e:
                            logger.error(f"Email failed: {e}")
                            
  
        elif event["type"] == "payment_intent.payment_failed":
            payment_intent = event["data"]["object"]
            record_id = payment_intent.get("metadata", {}).get("record_id")
            
            if record_id:
                record_result = self.supabase.table("ticket_records").select("*").eq("id", record_id).execute()
                if record_result.data:
                    record = record_result.data[0]
                    if record.get("payment_status") == "pending":
                        self.supabase.table("ticket_records").update({"payment_status": "failed"}).eq("id", record_id).execute()
                        
        return {"status": "ok"}
