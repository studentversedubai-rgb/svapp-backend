"""
Baitna enum values, labels and status sets.

The CHECK constraints in migrations/versions/20260904_add_baitna.sql mirror these
lists; test_baitna_service.TestEnumsAgree fails if they drift apart.
"""

from datetime import timedelta, timezone
from typing import Dict, FrozenSet, Optional, Tuple

# ================================
# DISPLAY LABELS
# ================================

UNIT_TYPE_LABELS: Dict[str, str] = {
    "en_suite": "En-suite Room",
    "studio": "Studio",
    "shared_twin": "Shared / Twin Room",
    "one_bed": "1-Bedroom Apartment",
    "two_bed": "2-Bedroom Apartment",
}

AVAILABILITY_LABELS: Dict[str, str] = {
    "available": "Available",
    "limited": "Limited Availability",
    "waitlist": "Waitlist",
    "unavailable": "Unavailable",
}

# budget_band and current_status are validated in schemas.py but not labelled
# here — only the partner dashboard displays them back.

# Student-facing wording; 'aging' reads as a plain wait to a student.
LEAD_STATUS_LABELS: Dict[str, str] = {
    "submitted": "Submitted",
    "posted_to_dashboard": "Awaiting Response",
    "acknowledged": "Acknowledged by Partner",
    "aging": "Awaiting Response",
    "converted": "Converted",
    "routed": "Rerouted to Another Partner",
    "withdrawn": "Withdrawn",
    "closed_no_match": "Closed",
    "expired_stale": "Expired",
}

PRICE_HIDDEN_DISPLAY = "Confirmed on inquiry"

# Mean Earth radius, the usual choice for a haversine distance.
EARTH_RADIUS_KM = 6371.0088


# Lead references are issued on the Asia/Dubai calendar day, so date validation
# uses the same clock. Dubai has no DST, so a fixed offset is exact and avoids a
# tzdata dependency on Windows.
DUBAI_TZ = timezone(timedelta(hours=4))

# Longest lead time accepted on a move-in date. Mainly catches year typos.
MOVE_IN_MAX_DAYS = 730


# ================================
# STATUS SETS
# ================================

# Live: not yet closed, so the student can still withdraw and the partner is
# still blocked from a second inquiry. 'acknowledged' belongs here — the partner
# has replied, but nothing is settled, and a student whose details have actually
# been read is the one who most needs the withdraw button. Kept in step with the
# baitna_leads_one_open_per_student_partner index and the BT001 check in the SQL.
OPEN_STATUSES: FrozenSet[str] = frozenset(
    {"submitted", "posted_to_dashboard", "acknowledged", "aging"}
)

# Entering any of these stamps closed_at and starts the 30-day floor.
# OPEN_STATUSES and TERMINAL_STATUSES partition LEAD_STATUS_LABELS exactly; a
# status in neither would report can_withdraw: false while withdraw() accepted it.
TERMINAL_STATUSES: FrozenSet[str] = frozenset(
    {"converted", "routed", "withdrawn", "closed_no_match", "expired_stale"}
)

# Switchable statuses. Narrower than OPEN_STATUSES on purpose: once a partner has
# acknowledged an inquiry they have read the student's details and started
# working that specific unit, so moving the lead under them changes what they
# already picked up. Withdrawing stays available on an acknowledged lead — see
# OPEN_STATUSES — because revoking consent has to work at every stage.
SWITCH_ELIGIBLE_STATUSES: FrozenSet[str] = frozenset(
    {"submitted", "posted_to_dashboard", "aging"}
)

# Reroutable statuses. Age is also required — see service.compute_can_fallback.
# Narrower than OPEN_STATUSES on purpose: 'acknowledged' means the partner did
# respond, so there is no silence to reroute away from.
FALLBACK_ELIGIBLE_STATUSES: FrozenSet[str] = frozenset(
    {"posted_to_dashboard", "aging"}
)

# Browse default, and the bar a listing must clear to be a reroute target.
# Waitlist units stay browsable on request; we just never route anyone into one.
BOOKABLE_AVAILABILITY: FrozenSet[str] = frozenset({"available", "limited"})


# ================================
# BROWSE FEED SORTING
# ================================

# Allow-listed `sort` values and the column each orders by. 'price' uses
# price_sort, not price_amount, so hidden prices sort to the end instead of
# landing between two visible neighbours and giving the figure away.
LISTING_SORTS: Dict[str, str] = {
    "popularity": "lead_count",
    "price": "price_sort",
    "area_sqft": "area_sqft",
    "bedrooms": "bedrooms",
    "newest": "created_at",
}

DEFAULT_LISTING_SORT = "popularity"
DEFAULT_LISTING_ORDER = "desc"


# ================================
# ERROR CODES
# ================================
# Sent in the `code` field so the app can branch without matching on English.
# Five are 409s and the status alone can't tell them apart.

CODE_OPEN_INQUIRY_EXISTS = "OPEN_INQUIRY_EXISTS"
CODE_COOLDOWN_ACTIVE = "COOLDOWN_ACTIVE"
CODE_PARTNER_NOT_FOUND = "PARTNER_NOT_FOUND"
CODE_LEAD_NOT_FOUND = "LEAD_NOT_FOUND"
CODE_NOT_FALLBACK_ELIGIBLE = "NOT_FALLBACK_ELIGIBLE"
CODE_NO_FALLBACK_MATCH = "NO_FALLBACK_MATCH"
CODE_ALREADY_CLOSED = "ALREADY_CLOSED"
CODE_MOVE_IN_DATE_REQUIRED = "MOVE_IN_DATE_REQUIRED"
CODE_STUDENT_NOT_FOUND = "STUDENT_NOT_FOUND"
CODE_EMAIL_FAILED = "EMAIL_FAILED"
CODE_INTERNAL = "INTERNAL_ERROR"

# Switching the unit on an open inquiry.
CODE_LISTING_NOT_FOUND = "LISTING_NOT_FOUND"
CODE_SAME_LISTING = "SAME_LISTING"
CODE_ALREADY_ACKNOWLEDGED = "ALREADY_ACKNOWLEDGED"
CODE_SWITCH_LIMIT_REACHED = "SWITCH_LIMIT_REACHED"

# SQLSTATEs raised by baitna_create_lead / its triggers.
SQLSTATE_OPEN_INQUIRY = "BT001"
SQLSTATE_COOLDOWN = "BT002"
SQLSTATE_PARTNER_INACTIVE = "BT003"
SQLSTATE_STUDENT_NOT_FOUND = "BT004"

# SQLSTATEs raised by baitna_switch_listing.
SQLSTATE_SWITCH_LEAD_NOT_FOUND = "BT005"
SQLSTATE_SWITCH_LEAD_CLOSED = "BT006"
SQLSTATE_SWITCH_LISTING_INVALID = "BT007"
SQLSTATE_SWITCH_SAME_LISTING = "BT008"
SQLSTATE_SWITCH_LIMIT = "BT009"
SQLSTATE_SWITCH_ACKNOWLEDGED = "BT010"

# Every SQLSTATE the module raises. _sqlstate_of falls back to scanning the
# string form of an exception for these, so a code missing here is read as an
# unknown failure and answered with a 500.
BAITNA_SQLSTATES: Tuple[str, ...] = (
    SQLSTATE_OPEN_INQUIRY,
    SQLSTATE_COOLDOWN,
    SQLSTATE_PARTNER_INACTIVE,
    SQLSTATE_STUDENT_NOT_FOUND,
    SQLSTATE_SWITCH_LEAD_NOT_FOUND,
    SQLSTATE_SWITCH_LEAD_CLOSED,
    SQLSTATE_SWITCH_LISTING_INVALID,
    SQLSTATE_SWITCH_SAME_LISTING,
    SQLSTATE_SWITCH_LIMIT,
    SQLSTATE_SWITCH_ACKNOWLEDGED,
)

# Postgres unique violation. The IF EXISTS guard inside baitna_create_lead is not
# atomic with the insert, so two submissions in flight at once both pass it and
# the partial unique index rejects the loser with this. Same conflict as BT001.
SQLSTATE_UNIQUE_VIOLATION = "23505"
OPEN_INQUIRY_INDEX = "baitna_leads_one_open_per_student_partner"


# ================================
# HELPERS
# ================================

def unit_type_label(value: str) -> str:
    return UNIT_TYPE_LABELS.get(value, value)


def availability_label(value: str) -> str:
    return AVAILABILITY_LABELS.get(value, value)


def lead_status_label(value: str) -> str:
    return LEAD_STATUS_LABELS.get(value, value)


def format_price(amount, currency: str = "AED") -> str:
    """'AED 3,500 / month'. Whole amounts drop the decimals."""
    if amount is None:
        return PRICE_HIDDEN_DISPLAY
    value = float(amount)
    if value.is_integer():
        return f"{currency} {int(value):,} / month"
    return f"{currency} {value:,.2f} / month"


def format_distance(km: Optional[float], university_name: Optional[str]) -> Optional[str]:
    """
    '3.4 km away from Heriot-Watt University Dubai'.

    None when either half is missing, which is the signal to the app that this
    line has nothing to show — a partner with no coordinates on file, or a
    student whose university we can't place, gets a tile with no distance rather
    than a tile claiming 0 km.
    """
    if km is None or not university_name:
        return None
    return f"{km:.1f} km away from {university_name}"
