"""
Baitna data access and business rules.

Submission goes through the baitna_create_lead Postgres function, not a series of
table writes: supabase-py cannot open a transaction, and a mid-flight failure would
leave orphan consent rows. Failures raise BaitnaError, never HTTPException — the
app-wide handler would rewrite our 404 messages and drop the structured payloads.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from app.core.config import get_settings
from app.core.database import get_supabase_client
from app.modules.baitna import constants as C
from app.modules.baitna.schemas import (
    BrowseListingRow,
    LeadCreateRequest,
    ListingFilters,
    ListingRow,
    PartnerTile,
    LeadRow,
)

logger = logging.getLogger(__name__)


# ================================
# ERRORS
# ================================

class BaitnaError(Exception):
    """A business-rule failure the client should see verbatim."""

    def __init__(
        self,
        status_code: int,
        message: str,
        code: Optional[str] = None,
        data: Optional[Dict] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code
        self.data = data


def _sqlstate_of(exc: Exception) -> Optional[str]:
    """SQLSTATE from a PostgREST error, falling back to scanning the string form
    since the exception type varies across supabase-py releases."""
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code:
        return code

    text = str(exc)
    for candidate in (
        C.SQLSTATE_OPEN_INQUIRY,
        C.SQLSTATE_COOLDOWN,
        C.SQLSTATE_PARTNER_INACTIVE,
        C.SQLSTATE_STUDENT_NOT_FOUND,
    ):
        if candidate in text:
            return candidate
    return None


def _error_message_of(exc: Exception) -> Optional[str]:
    message = getattr(exc, "message", None)
    if isinstance(message, str) and message:
        return message
    return None


def _error_detail_of(exc: Exception) -> Optional[str]:
    detail = getattr(exc, "details", None) or getattr(exc, "detail", None)
    if isinstance(detail, str) and detail:
        return detail
    return None


def _client():
    supabase = get_supabase_client()
    if supabase is None:
        logger.error("Baitna: Supabase client unavailable")
        raise BaitnaError(
            500,
            "Housing service is temporarily unavailable. Please try again later.",
            C.CODE_INTERNAL,
        )
    return supabase


# ================================
# PURE HELPERS
# ================================

def build_listing_row(listing: Dict, price_disclosed: bool) -> Dict:
    """Shape one listing. Price hiding is partner-level: when disclosure is off,
    every listing under that partner reports null and "Confirmed on inquiry"."""
    amount = listing.get("price_amount") if price_disclosed else None
    currency = listing.get("price_currency") or "AED"
    availability = listing.get("availability_status") or "available"
    unit_type = listing.get("unit_type") or ""

    spots = listing.get("spots_available")
    if spots is None:
        occ_max = listing.get("occupancy_max")
        occ_now = listing.get("occupants_current")
        if occ_max is not None and occ_now is not None:
            spots = occ_max - occ_now

    return ListingRow(
        id=str(listing.get("id")),
        unit_type=unit_type,
        unit_type_label=C.unit_type_label(unit_type),
        price_amount=float(amount) if amount is not None else None,
        price_currency=currency,
        price_display=C.format_price(amount, currency),
        image_urls=listing.get("image_urls") or [],
        availability_status=availability,
        availability_label=C.availability_label(availability),
        bedrooms=listing.get("bedrooms"),
        bathrooms=listing.get("bathrooms"),
        living_rooms=listing.get("living_rooms"),
        area_sqft=float(listing["area_sqft"]) if listing.get("area_sqft") is not None else None,
        occupancy_max=listing.get("occupancy_max"),
        occupants_current=listing.get("occupants_current"),
        spots_available=spots,
        lead_count=listing.get("lead_count") or 0,
    ).model_dump()


def build_browse_row(listing: Dict, partner: Dict) -> Dict:
    """A browse-feed row: the listing with its partner inline."""
    base = build_listing_row(listing, bool(partner.get("price_disclosure_enabled")))
    return BrowseListingRow(
        **base,
        partner_id=str(partner.get("id") or listing.get("partner_id")),
        partner_name=partner.get("name") or "",
        property_name=partner.get("property_name"),
        logo_url=partner.get("logo_url"),
    ).model_dump()


def _parse_ts(value) -> Optional[datetime]:
    """Postgres timestamptz string to an aware datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def compute_can_withdraw(status: str) -> bool:
    return status in C.OPEN_STATUSES


def compute_can_fallback(status: str, submitted_at, aging_days: Optional[int] = None) -> bool:
    """
    Reroutable once unacknowledged for BAITNA_AGING_DAYS.

    Measured from submitted_at, not from the `aging` status: that status is set by
    a job in the dashboard repo, and this must not wait on someone else's cron.
    """
    if status not in C.FALLBACK_ELIGIBLE_STATUSES:
        return False

    days = aging_days if aging_days is not None else get_settings().BAITNA_AGING_DAYS
    submitted = _parse_ts(submitted_at)
    if submitted is None:
        return False
    return datetime.now(timezone.utc) - submitted >= timedelta(days=days)


def build_lead_row(lead: Dict) -> Dict:
    """Shape one of the student's leads."""
    partner = lead.get("baitna_partners") or {}
    listing = lead.get("baitna_listings") or {}
    status = lead.get("status") or ""
    unit_type = listing.get("unit_type")

    return LeadRow(
        id=str(lead.get("id")),
        lead_reference=lead.get("lead_reference") or "",
        partner_name=partner.get("name") or "",
        property_name=partner.get("property_name"),
        unit_type=unit_type,
        unit_type_label=C.unit_type_label(unit_type) if unit_type else None,
        status=status,
        status_label=C.lead_status_label(status),
        submitted_at=_parse_ts(lead.get("submitted_at")),
        acknowledged_at=_parse_ts(lead.get("acknowledged_at")),
        can_withdraw=compute_can_withdraw(status),
        can_fallback=compute_can_fallback(status, lead.get("submitted_at")),
    ).model_dump()


# ================================
# SERVICE
# ================================

_LISTING_COLUMNS = (
    "id, partner_id, unit_type, price_amount, price_currency, availability_status,"
    " image_urls, bedrooms, bathrooms, living_rooms, area_sqft, occupancy_max,"
    " occupants_current, spots_available, lead_count, is_active, created_at"
)

# Upper bound on the fallback scan. Only the earliest unblocked listing is used,
# and blocked partners are already excluded server-side, so the first row is
# normally the answer; the rest is headroom for the degraded no-not_ path.
_FALLBACK_CANDIDATE_SCAN = 200

_PARTNER_EMBED = (
    "baitna_partners!inner(id, name, property_name, logo_url,"
    " price_disclosure_enabled, is_active)"
)


class BaitnaService:
    """Data access for the student-facing endpoints."""

    # ------------------------------------------------------------------
    # Tile visibility
    # ------------------------------------------------------------------
    def get_status(self) -> Dict:
        settings = get_settings()
        count = 0
        try:
            supabase = get_supabase_client()
            if supabase is not None:
                res = (
                    supabase.table("baitna_partners")
                    .select("id", count="exact")
                    .eq("is_active", True)
                    .execute()
                )
                count = res.count or 0
        except Exception as exc:
            # Polled on app launch, so a failure hides the tile rather than
            # breaking the launch screen.
            logger.error(f"Baitna: failed to count active partners: {exc}")
            count = 0

        return {
            "active_partner_count": count,
            "tile_visible": bool(count > 0 and settings.FEATURE_BAITNA_ENABLED),
        }

    # ------------------------------------------------------------------
    # Partner tiles
    # ------------------------------------------------------------------
    def list_partners(self) -> Dict:
        supabase = _client()
        try:
            res = (
                supabase.table("baitna_partners")
                .select(
                    "id, name, property_name, logo_url, price_disclosure_enabled,"
                    f" baitna_listings({_LISTING_COLUMNS})"
                )
                .eq("is_active", True)
                .order("created_at")
                .execute()
            )
        except Exception as exc:
            logger.error(f"Baitna: failed to list partners: {exc}")
            raise BaitnaError(500, "Could not load housing partners.", C.CODE_INTERNAL)

        partners: List[Dict] = []
        for row in res.data or []:
            disclosed = bool(row.get("price_disclosure_enabled"))
            listings = [
                build_listing_row(listing, disclosed)
                for listing in (row.get("baitna_listings") or [])
                if listing.get("is_active")
            ]
            partners.append(
                PartnerTile(
                    id=str(row.get("id")),
                    name=row.get("name") or "",
                    property_name=row.get("property_name"),
                    logo_url=row.get("logo_url"),
                    price_disclosure_enabled=disclosed,
                    listings=listings,
                ).model_dump()
            )

        return {"partners": partners}

    # ------------------------------------------------------------------
    # Browse feed
    # ------------------------------------------------------------------
    def browse_listings(self, filters: ListingFilters) -> Dict:
        supabase = _client()

        query = (
            supabase.table("baitna_listings")
            .select(f"{_LISTING_COLUMNS}, {_PARTNER_EMBED}", count="exact")
            .eq("is_active", True)
            .eq("baitna_partners.is_active", True)
        )

        if filters.unit_type:
            query = query.in_("unit_type", filters.unit_type)

        availability = filters.availability_status or sorted(C.BOOKABLE_AVAILABILITY)
        query = query.in_("availability_status", availability)

        if filters.partner_id:
            query = query.eq("partner_id", str(filters.partner_id))
        if filters.bedrooms_min is not None:
            query = query.gte("bedrooms", filters.bedrooms_min)
        if filters.bathrooms_min is not None:
            query = query.gte("bathrooms", filters.bathrooms_min)
        if filters.living_rooms_min is not None:
            query = query.gte("living_rooms", filters.living_rooms_min)
        if filters.area_sqft_min is not None:
            query = query.gte("area_sqft", filters.area_sqft_min)
        if filters.area_sqft_max is not None:
            query = query.lte("area_sqft", filters.area_sqft_max)
        if filters.has_spots_available:
            query = query.gt("spots_available", 0)

        # price_sort is NULL when the partner hides prices, so those listings drop
        # out of a range filter instead of being narrowed in on.
        if filters.price_min is not None:
            query = query.gte("price_sort", filters.price_min)
        if filters.price_max is not None:
            query = query.lte("price_sort", filters.price_max)

        query = self._apply_sort(query, filters)

        offset = (filters.page - 1) * filters.page_size
        query = query.range(offset, offset + filters.page_size - 1)

        try:
            res = query.execute()
        except Exception as exc:
            logger.error(f"Baitna: browse query failed: {exc}")
            raise BaitnaError(500, "Could not load listings.", C.CODE_INTERNAL)

        listings = []
        for row in res.data or []:
            partner = row.get("baitna_partners") or {}
            listings.append(build_browse_row(row, partner))

        return {
            "listings": listings,
            "page": filters.page,
            "page_size": filters.page_size,
            "total": res.count or 0,
        }

    @staticmethod
    def _apply_sort(query, filters: ListingFilters):
        """
        Requested key, then created_at as a stable tiebreaker so paging never
        repeats a row. Nulls sort last in both directions — see LISTING_SORTS.

        The order parameter is written directly rather than through the builder's
        order(): postgrest-py can only ever emit `.nullsfirst`, it has no
        nullslast option, so passing nullsfirst=False emits nothing at all and
        Postgres' own default takes over — which for DESC is NULLS FIRST. That
        put every hidden price at the top of sort=price (desc is the default
        order), and every listing with no bedroom or area data at the top of
        those sorts.
        """
        column = C.LISTING_SORTS[filters.sort]
        direction = "desc" if filters.order == "desc" else "asc"

        terms = [f"{column}.{direction}.nullslast"]
        # created_at is the tiebreaker, and is already the key for sort=newest.
        if column != "created_at":
            terms.append("created_at.desc.nullslast")
        order = ",".join(terms)

        try:
            query.params = query.params.set("order", order)
            return query
        except Exception as exc:
            # Never fail a browse over ordering: fall back to the builder call and
            # accept the null placement rather than 500.
            logger.warning(f"Baitna: could not set explicit order '{order}': {exc}")
            query = query.order(column, desc=(direction == "desc"))
            if column != "created_at":
                query = query.order("created_at", desc=True)
            return query

    # ------------------------------------------------------------------
    # The student's own leads
    # ------------------------------------------------------------------
    def list_student_leads(self, student_id: str) -> Dict:
        supabase = _client()
        try:
            res = (
                supabase.table("baitna_leads")
                .select(
                    "id, lead_reference, status, submitted_at, acknowledged_at,"
                    " baitna_partners(name, property_name),"
                    " baitna_listings(unit_type)"
                )
                .eq("student_id", student_id)
                .order("submitted_at", desc=True)
                .execute()
            )
        except Exception as exc:
            logger.error(f"Baitna: failed to list leads for {student_id}: {exc}")
            raise BaitnaError(500, "Could not load your inquiries.", C.CODE_INTERNAL)

        return {"leads": [build_lead_row(row) for row in (res.data or [])]}

    # ------------------------------------------------------------------
    # Submitting an inquiry
    # ------------------------------------------------------------------
    def create_lead(
        self,
        student_id: str,
        payload: LeadCreateRequest,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict:
        """Create consent + lead atomically. Returns the RPC payload."""
        return self._invoke_create_lead(
            student_id=student_id,
            partner_id=str(payload.partner_id),
            listing_id=str(payload.listing_id),
            move_in_date=payload.move_in_date.isoformat(),
            lease_length_months=payload.lease_length_months,
            budget_band=payload.budget_band,
            current_status=payload.current_status,
            consent_version=payload.consent.consent_version,
            consent_text_snapshot=payload.consent.consent_text_snapshot,
            data_transfers_outside_uae=payload.consent.data_transfers_outside_uae,
            dpo_contact=payload.consent.dpo_contact,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def _invoke_create_lead(self, **kwargs) -> Dict:
        supabase = _client()
        params = {
            "p_student_id": kwargs["student_id"],
            "p_partner_id": kwargs["partner_id"],
            "p_listing_id": kwargs["listing_id"],
            "p_move_in_date": kwargs["move_in_date"],
            "p_lease_length_months": kwargs["lease_length_months"],
            "p_budget_band": kwargs["budget_band"],
            "p_current_status": kwargs["current_status"],
            "p_consent_version": kwargs["consent_version"],
            "p_consent_text_snapshot": kwargs["consent_text_snapshot"],
            "p_data_transfers_outside_uae": kwargs.get("data_transfers_outside_uae", False),
            "p_dpo_contact": kwargs.get("dpo_contact"),
            "p_ip_address": kwargs.get("ip_address"),
            "p_user_agent": kwargs.get("user_agent"),
            "p_routed_from_lead_id": kwargs.get("routed_from_lead_id"),
        }

        try:
            res = supabase.rpc("baitna_create_lead", params).execute()
        except Exception as exc:
            raise self._translate_create_error(exc)

        lead = res.data
        if isinstance(lead, list):
            lead = lead[0] if lead else None
        if not lead:
            logger.error("Baitna: baitna_create_lead returned no row")
            raise BaitnaError(500, "Could not submit your inquiry.", C.CODE_INTERNAL)
        return lead

    @staticmethod
    def _translate_create_error(exc: Exception) -> BaitnaError:
        """Map the function's SQLSTATEs onto client errors."""
        sqlstate = _sqlstate_of(exc)

        # The double-tap: the same student submitting twice before the first
        # insert commits. Both clear the IF EXISTS check, then the partial unique
        # index rejects one. It is the same conflict BT001 describes, so it gets
        # the same answer instead of a 500 the student would just retry.
        if sqlstate == C.SQLSTATE_UNIQUE_VIOLATION:
            if C.OPEN_INQUIRY_INDEX not in str(exc):
                logger.error(f"Baitna: unexpected unique violation on create: {exc}")
            return BaitnaError(
                409,
                "You already have an open inquiry with this partner. "
                "Please wait for a response or withdraw it first.",
                C.CODE_OPEN_INQUIRY_EXISTS,
            )

        if sqlstate == C.SQLSTATE_OPEN_INQUIRY:
            return BaitnaError(
                409,
                "You already have an open inquiry with this partner. "
                "Please wait for a response or withdraw it first.",
                C.CODE_OPEN_INQUIRY_EXISTS,
            )

        if sqlstate == C.SQLSTATE_COOLDOWN:
            # The trigger puts the sentence in MESSAGE and the ISO date in DETAIL.
            eligible = _error_detail_of(exc)
            message = _error_message_of(exc) or (
                "You submitted an inquiry to this partner recently. "
                "Please try again later."
            )
            return BaitnaError(
                409,
                message,
                C.CODE_COOLDOWN_ACTIVE,
                {"eligible_from": eligible} if eligible else None,
            )

        if sqlstate == C.SQLSTATE_PARTNER_INACTIVE:
            return BaitnaError(
                404,
                "Partner or listing not found or not currently active.",
                C.CODE_PARTNER_NOT_FOUND,
            )

        if sqlstate == C.SQLSTATE_STUDENT_NOT_FOUND:
            # The id came from a valid JWT, so the profile row went missing mid
            # session. Re-authenticating is the only useful response.
            logger.error("Baitna: authenticated student has no public.users row")
            return BaitnaError(
                401,
                "Your account could not be found. Please sign in again.",
                C.CODE_STUDENT_NOT_FOUND,
            )

        logger.error(f"Baitna: baitna_create_lead failed: {exc}", exc_info=True)
        return BaitnaError(
            500, "Could not submit your inquiry. Please try again.", C.CODE_INTERNAL
        )

    # ------------------------------------------------------------------
    # Lead lookup shared by the three per-lead endpoints
    # ------------------------------------------------------------------
    def get_own_lead(self, student_id: str, lead_id: str) -> Dict:
        """
        Fetch one lead, scoped to its owner.

        The student_id filter is in the query rather than applied afterwards, so
        another student's lead is never read in the first place.
        """
        # A malformed id would otherwise reach Postgres as a failed cast and 500.
        try:
            UUID(str(lead_id))
        except (ValueError, AttributeError, TypeError):
            raise BaitnaError(404, "Lead not found.", C.CODE_LEAD_NOT_FOUND)

        supabase = _client()
        try:
            res = (
                supabase.table("baitna_leads")
                .select(
                    "*, baitna_partners(id, name, property_name, notification_emails),"
                    " baitna_listings(id, unit_type)"
                )
                .eq("id", lead_id)
                .eq("student_id", student_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            logger.error(f"Baitna: failed to fetch lead {lead_id}: {exc}")
            raise BaitnaError(500, "Could not load this inquiry.", C.CODE_INTERNAL)

        rows = res.data or []
        if not rows:
            raise BaitnaError(404, "Lead not found.", C.CODE_LEAD_NOT_FOUND)
        return rows[0]

    def get_resendable_lead(self, student_id: str, lead_id: str) -> Dict:
        """
        The lead behind a confirmation resend.

        Closed leads are refused: the confirmation tells the student their inquiry
        is with the partner and that a reply is coming within 7 days, which is
        untrue once the lead is closed and wrong on a withdrawn one, where they
        revoked consent for exactly that contact.
        """
        lead = self.get_own_lead(student_id, lead_id)
        if (lead.get("status") or "") not in C.OPEN_STATUSES:
            raise BaitnaError(
                409,
                "This inquiry is closed, so there is no confirmation to resend.",
                C.CODE_ALREADY_CLOSED,
            )
        return lead

    # ------------------------------------------------------------------
    # Rerouting a stalled inquiry
    # ------------------------------------------------------------------
    def route_fallback(
        self,
        student_id: str,
        lead_id: str,
        move_in_date: Optional[date] = None,
    ) -> Tuple[Dict, Dict]:
        """
        Reroute a stalled inquiry.

        Returns (response payload, new lead) — the second is what the caller needs
        for the notification emails.
        """
        settings = get_settings()
        original = self.get_own_lead(student_id, lead_id)

        if not compute_can_fallback(original.get("status") or "", original.get("submitted_at")):
            raise BaitnaError(
                409, "This lead is not eligible for rerouting.", C.CODE_NOT_FALLBACK_ELIGIBLE
            )

        listing = original.get("baitna_listings") or {}
        candidate = self._find_fallback_candidate(
            student_id=student_id,
            unit_type=listing.get("unit_type"),
            exclude_partner_id=original.get("partner_id"),
        )

        if candidate is None:
            raise BaitnaError(
                404,
                "No other matching partners are available right now. "
                "You can try searching on Dubizzle or Bayut.",
                C.CODE_NO_FALLBACK_MATCH,
                {
                    "dubizzle_url": settings.BAITNA_FALLBACK_DUBIZZLE_URL,
                    "bayut_url": settings.BAITNA_FALLBACK_BAYUT_URL,
                },
            )

        # A lead only becomes reroutable after a week of silence, so the original
        # date may have passed in the meantime. Carrying it over would hand the new
        # partner an inquiry for a date in the past.
        effective_move_in = move_in_date or _parse_date(original.get("move_in_date"))
        if effective_move_in is None or effective_move_in < datetime.now(C.DUBAI_TZ).date():
            raise BaitnaError(
                409,
                "Your original move-in date has passed. Please choose a new one.",
                C.CODE_MOVE_IN_DATE_REQUIRED,
                {"original_move_in_date": str(original.get("move_in_date") or "")},
            )

        consent = self._get_consent_event(original.get("consent_event_id"))

        # New consent naming the partner that actually receives the data.
        new_lead = self._invoke_create_lead(
            student_id=student_id,
            partner_id=candidate["partner_id"],
            listing_id=candidate["id"],
            move_in_date=effective_move_in.isoformat(),
            lease_length_months=original.get("lease_length_months"),
            budget_band=original.get("budget_band"),
            current_status=original.get("current_status"),
            consent_version=consent.get("consent_version") or settings.BAITNA_CONSENT_VERSION,
            # Guaranteed non-empty by _get_consent_event; never defaulted to "".
            consent_text_snapshot=consent["consent_text_snapshot"],
            data_transfers_outside_uae=consent.get("data_transfers_outside_uae", False),
            dpo_contact=consent.get("dpo_contact"),
            ip_address=consent.get("ip_address"),
            user_agent=consent.get("user_agent"),
            routed_from_lead_id=original.get("id"),
        )

        # Close the original only once the replacement exists.
        self._set_lead_status(original["id"], "routed")

        payload = {
            "new_lead_id": new_lead.get("id"),
            "new_lead_reference": new_lead.get("lead_reference"),
            "new_partner_name": new_lead.get("partner_name"),
            "original_lead_reference": original.get("lead_reference"),
            "original_lead_status": "routed",
            "move_in_date": effective_move_in.isoformat(),
            "message": f"Your inquiry has been rerouted to {new_lead.get('partner_name')}.",
        }
        return payload, new_lead

    def _find_fallback_candidate(
        self,
        student_id: str,
        unit_type: Optional[str],
        exclude_partner_id: Optional[str],
    ) -> Optional[Dict]:
        """First active listing of the same unit type from an unblocked partner.
        Earliest created wins, so the choice is explainable."""
        if not unit_type:
            return None

        supabase = _client()
        blocked = self._blocked_partner_ids(student_id)
        if exclude_partner_id:
            blocked.add(str(exclude_partner_id))

        query = (
            supabase.table("baitna_listings")
            .select(f"{_LISTING_COLUMNS}, {_PARTNER_EMBED}")
            .eq("is_active", True)
            .eq("baitna_partners.is_active", True)
            .eq("unit_type", unit_type)
            .in_("availability_status", sorted(C.BOOKABLE_AVAILABILITY))
        )

        # Exclude blocked partners in the query rather than after the fetch, so
        # this stays a small read as the catalogue grows. The loop below still
        # checks, since an older postgrest without not_ degrades to filtering here.
        if blocked:
            try:
                query = query.not_.in_("partner_id", sorted(blocked))
            except AttributeError:
                logger.warning(
                    "Baitna: postgrest builder has no not_; filtering candidates in Python"
                )

        try:
            res = query.order("created_at").limit(_FALLBACK_CANDIDATE_SCAN).execute()
        except Exception as exc:
            logger.error(f"Baitna: fallback candidate lookup failed: {exc}")
            raise BaitnaError(500, "Could not find another partner.", C.CODE_INTERNAL)

        for row in res.data or []:
            if str(row.get("partner_id")) not in blocked:
                return row
        return None

    def _blocked_partner_ids(self, student_id: str) -> set:
        """
        Partners with an open inquiry, or one closed inside the 30-day floor.

        Mirrors the database rules so a doomed reroute returns "no match" instead
        of a confusing 409.
        """
        supabase = _client()
        cooldown_days = get_settings().BAITNA_LEAD_COOLDOWN_DAYS
        cutoff = datetime.now(timezone.utc) - timedelta(days=cooldown_days)

        try:
            res = (
                supabase.table("baitna_leads")
                .select("partner_id, status, closed_at")
                .eq("student_id", student_id)
                .execute()
            )
        except Exception as exc:
            logger.error(f"Baitna: could not read student leads for blocking: {exc}")
            raise BaitnaError(500, "Could not find another partner.", C.CODE_INTERNAL)

        blocked = set()
        for row in res.data or []:
            partner_id = str(row.get("partner_id"))
            if row.get("status") in C.OPEN_STATUSES:
                blocked.add(partner_id)
                continue
            closed_at = _parse_ts(row.get("closed_at"))
            if closed_at is not None and closed_at > cutoff:
                blocked.add(partner_id)
        return blocked

    def _get_consent_event(self, consent_event_id: Optional[str]) -> Dict:
        """
        The consent record the reroute copies forward.

        Raises rather than degrading to {}. The snapshot is the legal record of
        what the student agreed to, and consent_events.consent_text_snapshot is
        only NOT NULL — an empty string would satisfy the column and leave the new
        lead with no evidence behind it. baitna_leads.consent_event_id is NOT NULL,
        so a missing row here means data loss, not an ordinary empty result.
        """
        if not consent_event_id:
            logger.error("Baitna: lead has no consent_event_id; cannot reroute")
            raise BaitnaError(
                500, "Could not carry your consent across. Please try again.", C.CODE_INTERNAL
            )

        supabase = _client()
        try:
            res = (
                supabase.table("consent_events")
                .select("*")
                .eq("id", consent_event_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            logger.error(f"Baitna: could not read consent event {consent_event_id}: {exc}")
            raise BaitnaError(
                500, "Could not carry your consent across. Please try again.", C.CODE_INTERNAL
            )

        rows = res.data or []
        consent = rows[0] if rows else {}
        if not (consent.get("consent_text_snapshot") or "").strip():
            logger.error(
                f"Baitna: consent event {consent_event_id} is missing or has an "
                f"empty snapshot; refusing to reroute without a consent record"
            )
            raise BaitnaError(
                500, "Could not carry your consent across. Please try again.", C.CODE_INTERNAL
            )
        return consent

    def _set_lead_status(self, lead_id: str, status: str) -> None:
        """Status only — closed_at is stamped by the trigger, so no code path can
        forget it and break the 30-day floor."""
        supabase = _client()
        try:
            supabase.table("baitna_leads").update({"status": status}).eq("id", lead_id).execute()
        except Exception as exc:
            logger.error(f"Baitna: failed to set lead {lead_id} to {status}: {exc}")
            raise BaitnaError(500, "Could not update this inquiry.", C.CODE_INTERNAL)

    # ------------------------------------------------------------------
    # Withdrawing consent
    # ------------------------------------------------------------------
    def withdraw(self, student_id: str, lead_id: str, reason: Optional[str]) -> Dict:
        lead = self.get_own_lead(student_id, lead_id)
        status = lead.get("status") or ""

        if status in C.TERMINAL_STATUSES:
            raise BaitnaError(
                409, "This lead has already been closed or withdrawn.", C.CODE_ALREADY_CLOSED
            )

        supabase = _client()
        withdrawn_at = datetime.now(timezone.utc)

        consent_event_id = lead.get("consent_event_id")
        if consent_event_id:
            try:
                (
                    supabase.table("consent_events")
                    .update(
                        {
                            "withdrawn_at": withdrawn_at.isoformat(),
                            "withdrawal_reason": reason,
                        }
                    )
                    .eq("id", consent_event_id)
                    .execute()
                )
            except Exception as exc:
                # The consent record is the point of this endpoint; never close
                # the lead claiming consent was revoked when it was not.
                logger.error(f"Baitna: failed to withdraw consent {consent_event_id}: {exc}")
                raise BaitnaError(
                    500, "Could not withdraw your consent. Please try again.", C.CODE_INTERNAL
                )

        self._set_lead_status(lead["id"], "withdrawn")

        return {
            "lead_reference": lead.get("lead_reference"),
            "status": "withdrawn",
            "withdrawn_at": withdrawn_at,
            "message": "Your inquiry has been withdrawn and your consent has been revoked.",
        }

    # ------------------------------------------------------------------
    # Notification bookkeeping
    # ------------------------------------------------------------------
    def mark_partner_notified(self, lead_id: str, sent: bool) -> None:
        """Best-effort record of whether the partner notice went out."""
        supabase = get_supabase_client()
        if supabase is None:
            return
        try:
            payload = {"notification_sent": sent}
            if sent:
                payload["notification_sent_at"] = datetime.now(timezone.utc).isoformat()
            supabase.table("baitna_leads").update(payload).eq("id", lead_id).execute()
        except Exception as exc:
            logger.error(f"Baitna: could not record notification state for {lead_id}: {exc}")
