"""
Plain-text notices, sent through the existing Postmark integration.

Everything goes through _safe_send: EmailService raises on failure, and a Postmark
outage must not fail a lead that is already committed.
"""

import logging
from datetime import date
from typing import Dict, List, Optional

from app.core.config import get_settings
from app.core.email import EmailService
from app.modules.baitna.constants import unit_type_label

logger = logging.getLogger(__name__)


def _safe_send(email: str, subject: str, body: str) -> bool:
    """Returns True only on a confirmed send."""
    if not email:
        return False
    try:
        EmailService.send_text_email(email, subject, body)
        return True
    except Exception as exc:
        logger.error(
            f"Baitna email failed. To: {email}, Subject: {subject}, "
            f"ErrorType: {type(exc).__name__}, Detail: {exc}"
        )
        return False


def student_greeting(user: Dict) -> str:
    """
    'Sarah' from first_name, else the first word of the display name.

    The display column on public.users is `name`, which the auth service keeps in
    step with first_name + last_name. There is no full_name column — reading one
    greets every student as "there". Some signup paths fill only one of the two,
    so both are tried.
    """
    first = (user.get("first_name") or "").strip()
    if first:
        return first
    full = (user.get("name") or "").strip()
    if full:
        return full.split()[0]
    return "there"


def _move_in_display(value) -> str:
    """'October 2026'."""
    if not value:
        return "Not specified"
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value[:10])
        except ValueError:
            return value
    return value.strftime("%B %Y")


def send_student_confirmation(
    to_email: str,
    user: Dict,
    lead: Dict,
) -> bool:
    """Sent on submission and on resend."""
    reference = lead.get("lead_reference", "")
    partner_name = lead.get("partner_name", "the partner")
    property_name = lead.get("property_name") or partner_name

    subject = f"Your Baitna Inquiry - {reference}"
    body = (
        f"Hi {student_greeting(user)},\n\n"
        f"Your housing inquiry has been submitted to {partner_name} ({property_name}).\n\n"
        f"Lead Reference: {reference}\n"
        f"Unit Type: {unit_type_label(lead.get('unit_type', ''))}\n"
        f"Desired Move-in: {_move_in_display(lead.get('move_in_date'))}\n\n"
        "The partner typically responds within 7 days. You can check your inquiry\n"
        "status anytime in the Baitna section of your StudentVerse app."
    )
    return _safe_send(to_email, subject, body)


def send_partner_notification(
    recipients: Optional[List[str]],
    lead: Dict,
) -> bool:
    """
    Notice to the partner's operations addresses.

    Recipients come from baitna_partners.notification_emails, not from the
    dashboard logins — a partner can receive leads before anyone has an account.
    True if at least one address accepted it.
    """
    if not recipients:
        logger.warning(
            f"Baitna lead {lead.get('lead_reference')} has no partner notification "
            f"emails configured; skipping partner notice."
        )
        return False

    reference = lead.get("lead_reference", "")
    partner_name = lead.get("partner_name", "")
    dashboard_url = get_settings().BAITNA_DASHBOARD_URL or "your Baitna dashboard"

    subject = f"New Student Inquiry - {reference}"
    body = (
        f"Hi {partner_name} Team,\n\n"
        "A new student inquiry has been submitted through StudentVerse Baitna.\n\n"
        f"Lead Reference: {reference}\n"
        f"Unit Type: {unit_type_label(lead.get('unit_type', ''))}\n\n"
        "Please log in to your dashboard to view the full details and acknowledge\n"
        f"this inquiry: {dashboard_url}"
    )

    results = [_safe_send(address, subject, body) for address in recipients]
    return any(results)
