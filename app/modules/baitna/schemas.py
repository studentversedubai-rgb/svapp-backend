"""Request bodies, browse-feed filters, and the response row shapes."""

from datetime import date, datetime, timedelta
from typing import List, Literal, Optional
from uuid import UUID

from fastapi import Query
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, field_validator

from app.core.config import get_settings
from app.modules.baitna.constants import (
    DEFAULT_LISTING_ORDER,
    DEFAULT_LISTING_SORT,
    DUBAI_TZ,
    MOVE_IN_MAX_DAYS,
)

# ================================
# ENUM TYPES
# ================================
# Literals so FastAPI rejects unknown values with a 422 before they reach the
# query builder. TestEnumsAgree keeps them in step with constants.py and the SQL.

UnitType = Literal["en_suite", "studio", "shared_twin", "one_bed", "two_bed"]
AvailabilityStatus = Literal["available", "limited", "waitlist", "unavailable"]
BudgetBand = Literal[
    "under_2000", "2000_3500", "3500_5000", "5000_8000", "above_8000"
]
CurrentStatus = Literal[
    "in_university_housing", "in_private_housing", "arriving_soon", "looking_to_move"
]
ListingSort = Literal["popularity", "price", "area_sqft", "bedrooms", "newest"]
SortOrder = Literal["asc", "desc"]


# ================================
# REQUESTS
# ================================

def validate_move_in_date(value: date) -> date:
    """
    Neither pydantic's `date` type nor the database has an opinion on which dates
    make sense, so a mistyped year would reach the partner as a real inquiry.
    """
    today = datetime.now(DUBAI_TZ).date()
    if value < today:
        raise ValueError("Move-in date cannot be in the past.")
    if value > today + timedelta(days=MOVE_IN_MAX_DAYS):
        raise ValueError("Move-in date is too far in the future.")
    return value


class ConsentPayload(BaseModel):
    """
    The copy lives in the mobile app; we store whatever it sends, verbatim, tagged
    with consent_version, so the record matches what the student actually saw.
    """

    consent_version: str = Field(..., min_length=1, max_length=64)
    consent_text_snapshot: str = Field(..., min_length=1)
    data_transfers_outside_uae: bool = False
    dpo_contact: Optional[str] = Field(None, max_length=255)


class LeadCreateRequest(BaseModel):
    # UUID-typed so a malformed id is a 422, not a Postgres cast error as a 500.
    partner_id: UUID
    listing_id: UUID
    move_in_date: date
    lease_length_months: int = Field(..., ge=1, le=60)
    budget_band: BudgetBand
    current_status: CurrentStatus
    consent: ConsentPayload

    @field_validator("move_in_date")
    @classmethod
    def _sane_move_in_date(cls, value: date) -> date:
        return validate_move_in_date(value)


class FallbackRouteRequest(BaseModel):
    """
    Optional body for rerouting. Omit it to carry the original date across; send a
    new one when the original has passed while the student was waiting.
    """

    move_in_date: Optional[date] = None

    @field_validator("move_in_date")
    @classmethod
    def _sane_move_in_date(cls, value: Optional[date]) -> Optional[date]:
        return validate_move_in_date(value) if value is not None else value


class WithdrawRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=1000)


# ================================
# BROWSE FEED FILTERS
# ================================

def _range_error(low_field: str, high_field: str, value) -> RequestValidationError:
    """Shaped like a pydantic field error so it lands in the same 422 envelope."""
    return RequestValidationError(
        [
            {
                "type": "value_error",
                "loc": ("query", low_field),
                "msg": f"Input should be less than or equal to {high_field}",
                "input": value,
            }
        ]
    )


def resolve_page_size(
    requested: Optional[int],
    default: Optional[int] = None,
    maximum: Optional[int] = None,
) -> int:
    """
    Clamp rather than reject — an oversized page_size is a client bug, not a
    reason to fail the request. Bounds are injectable so tests skip settings.
    """
    if default is None or maximum is None:
        settings = get_settings()
        default = default if default is not None else settings.BAITNA_LISTINGS_PAGE_SIZE
        maximum = maximum if maximum is not None else settings.BAITNA_LISTINGS_MAX_PAGE_SIZE
    return min(requested or default, maximum)


class ListingFilters:
    """
    Query parameters for GET /baitna/listings.

    A plain class rather than a Pydantic model so the repeatable params bind
    correctly as lists.
    """

    def __init__(
        self,
        unit_type: Optional[List[UnitType]] = Query(
            None, description="Repeatable. Defaults to all unit types."
        ),
        availability_status: Optional[List[AvailabilityStatus]] = Query(
            None,
            description=(
                "Repeatable. Defaults to available + limited so students aren't "
                "shown units that cannot house them."
            ),
        ),
        partner_id: Optional[UUID] = Query(None),
        bedrooms_min: Optional[int] = Query(None, ge=0),
        bathrooms_min: Optional[int] = Query(None, ge=0),
        living_rooms_min: Optional[int] = Query(None, ge=0),
        area_sqft_min: Optional[float] = Query(None, gt=0),
        area_sqft_max: Optional[float] = Query(None, gt=0),
        price_min: Optional[float] = Query(None, ge=0),
        price_max: Optional[float] = Query(None, ge=0),
        has_spots_available: Optional[bool] = Query(
            None, description="True keeps only listings with occupants_current < occupancy_max."
        ),
        sort: ListingSort = Query(DEFAULT_LISTING_SORT),
        order: SortOrder = Query(DEFAULT_LISTING_ORDER),
        page: int = Query(1, ge=1),
        page_size: Optional[int] = Query(
            None, ge=1, description="Defaults to 20, clamped to 50."
        ),
    ) -> None:
        # RequestValidationError, not HTTPException, so these get the same 422
        # envelope as FastAPI's own field errors instead of a second shape.
        if area_sqft_min is not None and area_sqft_max is not None and area_sqft_min > area_sqft_max:
            raise _range_error("area_sqft_min", "area_sqft_max", area_sqft_min)
        if price_min is not None and price_max is not None and price_min > price_max:
            raise _range_error("price_min", "price_max", price_min)

        self.unit_type = unit_type or None
        self.availability_status = availability_status or None
        self.partner_id = partner_id
        self.bedrooms_min = bedrooms_min
        self.bathrooms_min = bathrooms_min
        self.living_rooms_min = living_rooms_min
        self.area_sqft_min = area_sqft_min
        self.area_sqft_max = area_sqft_max
        self.price_min = price_min
        self.price_max = price_max
        self.has_spots_available = has_spots_available
        self.sort = sort
        self.order = order
        self.page = page
        self.page_size = resolve_page_size(page_size)


# ================================
# RESPONSE ROWS
# ================================

class ListingRow(BaseModel):
    """One unit, in both the partner tile and the browse feed."""

    id: str
    unit_type: str
    unit_type_label: str

    price_amount: Optional[float] = None
    price_currency: str = "AED"
    price_display: str

    image_urls: List[str] = Field(default_factory=list)
    availability_status: str
    availability_label: str

    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    living_rooms: Optional[int] = None
    area_sqft: Optional[float] = None
    occupancy_max: Optional[int] = None
    occupants_current: Optional[int] = None
    spots_available: Optional[int] = None
    lead_count: int = 0


class BrowseListingRow(ListingRow):
    """A browse-feed row, carrying its partner inline."""

    partner_id: str
    partner_name: str
    property_name: Optional[str] = None
    logo_url: Optional[str] = None


class PartnerTile(BaseModel):
    id: str
    name: str
    property_name: Optional[str] = None
    logo_url: Optional[str] = None
    price_disclosure_enabled: bool
    listings: List[ListingRow] = Field(default_factory=list)


class LeadRow(BaseModel):
    id: str
    lead_reference: str
    partner_name: str
    property_name: Optional[str] = None
    unit_type: Optional[str] = None
    unit_type_label: Optional[str] = None
    status: str
    status_label: str
    submitted_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    can_withdraw: bool
    can_fallback: bool
