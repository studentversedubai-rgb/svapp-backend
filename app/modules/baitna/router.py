"""
Student-facing housing inquiry endpoints, mounted at /baitna.

Routes return JSONResponse rather than raising, so our messages and payloads
survive the app-wide handler. The feature-flag gate and the rate limiter are the
exceptions — both raise on purpose, and their responses are fine as-is.
"""

import logging
from typing import Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from app.core.config import get_settings
from app.core.security import get_current_user
from app.middleware.ratelimit import RateLimiter
from app.modules.baitna import constants as C
from app.modules.baitna import emails
from app.modules.baitna.dependencies import require_baitna_enabled
from app.modules.baitna.responses import baitna_error, baitna_ok
from app.modules.baitna.schemas import (
    FallbackRouteRequest,
    LeadCreateRequest,
    ListingFilters,
    WithdrawRequest,
)
from app.modules.baitna.service import BaitnaError, BaitnaService

logger = logging.getLogger(__name__)

router = APIRouter()


# ================================
# DEPENDENCY INJECTION
# ================================

def get_baitna_service() -> BaitnaService:
    return BaitnaService()


# ================================
# HELPERS
# ================================

def _client_ip(request: Request) -> str:
    """
    Caller IP for the consent record.

    Counts back from the right of X-Forwarded-For past our own proxies, so a
    client-supplied header cannot spoof what we store.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            hops = max(1, get_settings().RATE_LIMIT_PROXY_HOPS)
            return parts[max(0, len(parts) - hops)]
    return getattr(request.client, "host", "") or ""


def _send_lead_notifications(
    service: BaitnaService,
    user: Dict,
    lead: Dict,
) -> None:
    """
    Student confirmation + partner notice, after the response so a slow Postmark
    never turns a committed lead into a 500. Only the partner result is persisted.
    """
    try:
        emails.send_student_confirmation(user.get("email"), user, lead)
        partner_sent = emails.send_partner_notification(
            lead.get("notification_emails"), lead
        )
        service.mark_partner_notified(lead.get("id"), partner_sent)
    except Exception as exc:
        logger.error(f"Baitna: notification task failed for {lead.get('id')}: {exc}")


# ================================
# GET /baitna/status — public
# ================================

@router.get(
    "/status",
    summary="Baitna tile visibility",
    description=(
        "Public. Returns the number of active housing partners and whether the "
        "Baitna tile should be shown. Deliberately not gated by the feature flag: "
        "the app calls this to decide whether to render the tile, and answers "
        "tile_visible: false rather than 404 when the feature is off."
    ),
)
async def get_baitna_status(
    service: BaitnaService = Depends(get_baitna_service),
):
    # get_status() swallows its own failures and reports zero partners: on launch,
    # a hidden tile beats a broken home screen.
    return baitna_ok(service.get_status())


# ================================
# GET /baitna/partners
# ================================

@router.get(
    "/partners",
    dependencies=[Depends(require_baitna_enabled)],
    summary="Active partners and their listings",
    description=(
        "Requires a student JWT. Returns every active partner with its active "
        "listings. When a partner has price_disclosure_enabled off, all of its "
        "listings report a null price and 'Confirmed on inquiry'."
    ),
)
async def list_partners(
    current_user: Dict = Depends(get_current_user),
    service: BaitnaService = Depends(get_baitna_service),
):
    try:
        return baitna_ok(service.list_partners())
    except BaitnaError as exc:
        return baitna_error(exc.status_code, exc.message, exc.code, exc.data)


# ================================
# GET /baitna/listings
# ================================

@router.get(
    "/listings",
    dependencies=[Depends(require_baitna_enabled)],
    summary="Browse listings with filters and sorting",
    description=(
        "Requires a student JWT. Flat, paginated feed across all active partners. "
        "Filter by unit type, partner, bedrooms, bathrooms, living rooms, area, "
        "price and remaining spots; sort by price, popularity, area, bedrooms or "
        "newest.\n\n"
        "Listings whose partner has price disclosure switched off are excluded "
        "from price range filters and sort last under sort=price, so the filters "
        "cannot be used to work out a hidden price."
    ),
)
async def browse_listings(
    filters: ListingFilters = Depends(),
    current_user: Dict = Depends(get_current_user),
    service: BaitnaService = Depends(get_baitna_service),
):
    try:
        return baitna_ok(service.browse_listings(filters))
    except BaitnaError as exc:
        return baitna_error(exc.status_code, exc.message, exc.code, exc.data)


# ================================
# GET /baitna/leads
# ================================

@router.get(
    "/leads",
    dependencies=[Depends(require_baitna_enabled)],
    summary="The student's own inquiries",
)
async def list_leads(
    current_user: Dict = Depends(get_current_user),
    service: BaitnaService = Depends(get_baitna_service),
):
    try:
        return baitna_ok(service.list_student_leads(current_user["id"]))
    except BaitnaError as exc:
        return baitna_error(exc.status_code, exc.message, exc.code, exc.data)


# ================================
# POST /baitna/leads
# ================================

@router.post(
    "/leads",
    dependencies=[Depends(require_baitna_enabled)],
    summary="Submit a housing inquiry",
    description=(
        "Requires a student JWT. Records consent and creates the lead atomically, "
        "then queues the student confirmation and the partner notice.\n\n"
        "409 OPEN_INQUIRY_EXISTS when an inquiry with this partner is still open; "
        "409 COOLDOWN_ACTIVE when one closed within the last 30 days (the eligible "
        "date is in data.eligible_from); 404 PARTNER_NOT_FOUND when the partner or "
        "listing is missing or inactive."
    ),
)
async def create_lead(
    payload: LeadCreateRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: Dict = Depends(get_current_user),
    service: BaitnaService = Depends(get_baitna_service),
):
    RateLimiter.check_generic_limit(
        key=f"rl:baitna:submit:{current_user['id']}",
        limit=5,
        window=3600,
        error_message="You've submitted several inquiries recently. Please try again later.",
    )

    try:
        lead = service.create_lead(
            student_id=current_user["id"],
            payload=payload,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
        )
    except BaitnaError as exc:
        return baitna_error(exc.status_code, exc.message, exc.code, exc.data)

    background_tasks.add_task(_send_lead_notifications, service, current_user, lead)

    return baitna_ok(
        {
            "id": lead.get("id"),
            "lead_reference": lead.get("lead_reference"),
            "status": lead.get("status"),
            "partner_name": lead.get("partner_name"),
            "submitted_at": lead.get("submitted_at"),
            "message": (
                "Your inquiry has been submitted. "
                "You'll receive an email confirmation shortly."
            ),
        },
        status_code=201,
    )


# ================================
# POST /baitna/leads/{lead_id}/fallback/route
# ================================

@router.post(
    "/leads/{lead_id}/fallback/route",
    dependencies=[Depends(require_baitna_enabled)],
    summary="Reroute a stalled inquiry to another partner",
    description=(
        "Requires a student JWT. Finds another active partner with an available "
        "listing of the same unit type that the student isn't already blocked on, "
        "creates a new lead with a fresh consent record naming that partner, and "
        "marks the original as routed.\n\n"
        "Body is optional: send move_in_date to pick a new one, omit it to keep "
        "the original.\n\n"
        "When nothing matches, returns 404 NO_FALLBACK_MATCH with Dubizzle and "
        "Bayut URLs in `data`."
    ),
)
async def route_fallback(
    lead_id: str,
    background_tasks: BackgroundTasks,
    payload_in: Optional[FallbackRouteRequest] = None,
    current_user: Dict = Depends(get_current_user),
    service: BaitnaService = Depends(get_baitna_service),
):
    # Same budget as submission, which is what this is: it mints a lead through
    # baitna_create_lead and emails a partner. Reroutes are naturally scarce (a
    # lead has to sit unanswered for a week first), so this only catches a client
    # retrying in a loop.
    RateLimiter.check_generic_limit(
        key=f"rl:baitna:submit:{current_user['id']}",
        limit=5,
        window=3600,
        error_message="You've submitted several inquiries recently. Please try again later.",
    )

    try:
        payload, new_lead = service.route_fallback(
            current_user["id"],
            lead_id,
            move_in_date=payload_in.move_in_date if payload_in else None,
        )
    except BaitnaError as exc:
        return baitna_error(exc.status_code, exc.message, exc.code, exc.data)

    background_tasks.add_task(_send_lead_notifications, service, current_user, new_lead)

    return baitna_ok(payload, status_code=201)


# ================================
# POST /baitna/leads/{lead_id}/fallback/resend
# ================================

@router.post(
    "/leads/{lead_id}/fallback/resend",
    dependencies=[Depends(require_baitna_enabled)],
    summary="Resend the confirmation email",
    description=(
        "Requires a student JWT. Re-sends the student's confirmation for an "
        "existing lead. Changes nothing about the lead."
    ),
)
async def resend_confirmation(
    lead_id: str,
    current_user: Dict = Depends(get_current_user),
    service: BaitnaService = Depends(get_baitna_service),
):
    RateLimiter.check_generic_limit(
        key=f"rl:baitna:resend:{current_user['id']}",
        limit=3,
        window=3600,
        error_message="Please wait before requesting another email.",
    )

    try:
        # Refuses closed leads: see BaitnaService.get_resendable_lead.
        lead = service.get_resendable_lead(current_user["id"], lead_id)
    except BaitnaError as exc:
        return baitna_error(exc.status_code, exc.message, exc.code, exc.data)

    partner = lead.get("baitna_partners") or {}
    listing = lead.get("baitna_listings") or {}

    # Inline, not backgrounded: the email is the response, so a failure should be
    # reported rather than hidden behind a success message.
    sent = emails.send_student_confirmation(
        current_user.get("email"),
        current_user,
        {
            "lead_reference": lead.get("lead_reference"),
            "partner_name": partner.get("name"),
            "property_name": partner.get("property_name"),
            "unit_type": listing.get("unit_type"),
            "move_in_date": lead.get("move_in_date"),
        },
    )

    if not sent:
        return baitna_error(
            502,
            "We couldn't send the email right now. Please try again shortly.",
            C.CODE_EMAIL_FAILED,
        )

    return baitna_ok({"message": "Confirmation email resent to your registered email."})


# ================================
# POST /baitna/leads/{lead_id}/consent/withdraw
# ================================

@router.post(
    "/leads/{lead_id}/consent/withdraw",
    dependencies=[Depends(require_baitna_enabled)],
    summary="Withdraw consent and close the inquiry",
    description=(
        "Requires a student JWT. Marks the consent record withdrawn and closes the "
        "lead. Withdrawal is terminal: it starts the 30-day floor on new inquiries "
        "to the same partner."
    ),
)
async def withdraw_consent(
    lead_id: str,
    payload: Optional[WithdrawRequest] = None,
    current_user: Dict = Depends(get_current_user),
    service: BaitnaService = Depends(get_baitna_service),
):
    # reason is optional, so the whole body is too.
    reason = payload.reason if payload else None
    try:
        result = service.withdraw(current_user["id"], lead_id, reason)
        return baitna_ok(result)
    except BaitnaError as exc:
        return baitna_error(exc.status_code, exc.message, exc.code, exc.data)
