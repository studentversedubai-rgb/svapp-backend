"""
Unit Tests for the Baitna Service

Pure unit tests with stubbed Supabase access, matching the style of
test_offer_service.py — this repo has no TestClient or database fixtures.

The database-enforced rules (one open inquiry, the 30-day floor, the daily
reference sequence) are verified with SQL against a Supabase branch; see the
verification block at the bottom of
migrations/versions/20260904_add_baitna.sql.
"""

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import get_args

import pytest
from httpx import QueryParams
from pydantic import ValidationError

from app.modules.baitna import constants as C
from app.modules.baitna.emails import student_greeting
from app.modules.baitna.schemas import (
    AvailabilityStatus,
    BudgetBand,
    CurrentStatus,
    FallbackRouteRequest,
    LeadCreateRequest,
    ListingSort,
    ListingSwitchRequest,
    UnitType,
    resolve_page_size,
)
from app.modules.baitna.service import (
    BaitnaError,
    BaitnaService,
    build_lead_row,
    build_listing_row,
    build_partner_distance,
    compute_can_fallback,
    compute_can_switch_listing,
    compute_can_withdraw,
    compute_switches_remaining,
    haversine_km,
)


# ================================
# FIXTURES / STUBS
# ================================

def _listing(**overrides):
    base = {
        "id": "listing-1",
        "partner_id": "partner-1",
        "unit_type": "studio",
        "price_amount": 3500,
        "price_currency": "AED",
        "availability_status": "available",
        "image_urls": ["https://example.com/a.jpg"],
        "bedrooms": 1,
        "bathrooms": 1,
        "living_rooms": 0,
        "area_sqft": 480,
        "occupancy_max": 2,
        "occupants_current": 1,
        "spots_available": 1,
        "lead_count": 7,
    }
    base.update(overrides)
    return base


class FakeQuery:
    """
    Records every builder call so a test can assert on the predicates the service
    emitted, without a live PostgREST connection.
    """

    def __init__(self, rows=None, count=0):
        self.calls = []
        self._rows = rows if rows is not None else []
        self._count = count
        # The real builder keeps its query string here, and _apply_sort writes the
        # order parameter straight into it. Using the same type as postgrest means
        # these tests see the parameter the server would actually receive, not
        # just the arguments we handed the library.
        self.params = QueryParams()

    def order_param(self):
        return self.params.get("order")

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        return self

    def select(self, *a, **k):
        return self._record("select", *a, **k)

    def eq(self, *a, **k):
        return self._record("eq", *a, **k)

    def in_(self, *a, **k):
        return self._record("in_", *a, **k)

    def gte(self, *a, **k):
        return self._record("gte", *a, **k)

    def lte(self, *a, **k):
        return self._record("lte", *a, **k)

    def gt(self, *a, **k):
        return self._record("gt", *a, **k)

    def ilike(self, *a, **k):
        return self._record("ilike", *a, **k)

    def order(self, *a, **k):
        return self._record("order", *a, **k)

    def range(self, *a, **k):
        return self._record("range", *a, **k)

    def limit(self, *a, **k):
        return self._record("limit", *a, **k)

    @property
    def not_(self):
        """Mirrors postgrest's `.not_.in_(...)` proxy, recorded as 'not_in_'."""
        outer = self

        class _Not:
            def in_(self, *a, **k):
                return outer._record("not_in_", *a, **k)

        return _Not()

    def update(self, *a, **k):
        return self._record("update", *a, **k)

    def insert(self, *a, **k):
        return self._record("insert", *a, **k)

    def execute(self):
        self.calls.append(("execute", (), {}))
        return type("Res", (), {"data": self._rows, "count": self._count})()

    # Assertion helpers -------------------------------------------------
    def filters(self, name):
        return [(a, k) for (call, a, k) in self.calls if call == name]

    def has_filter(self, name, column, value=None):
        for args, _ in self.filters(name):
            if args and args[0] == column and (value is None or args[1] == value):
                return True
        return False


class FakeSupabase:
    def __init__(self, query):
        self.query = query
        self.requested_tables = []

    def table(self, name):
        self.requested_tables.append(name)
        return self.query


class StubFilters:
    """
    Duck-typed stand-in for ListingFilters. The real class carries FastAPI Query
    objects as defaults, so it can only be constructed through a request.
    """

    def __init__(self, **overrides):
        defaults = dict(
            unit_type=None,
            availability_status=None,
            partner_id=None,
            bedrooms_min=None,
            bathrooms_min=None,
            living_rooms_min=None,
            area_sqft_min=None,
            area_sqft_max=None,
            price_min=None,
            price_max=None,
            has_spots_available=None,
            sort="popularity",
            order="desc",
            page=1,
            page_size=20,
        )
        defaults.update(overrides)
        for key, value in defaults.items():
            setattr(self, key, value)


@pytest.fixture
def service():
    return BaitnaService()


# ================================
# PRICE HIDING AND LABELS
# ================================

class TestListingShape:
    def test_price_shown_when_partner_discloses(self):
        row = build_listing_row(_listing(), price_disclosed=True)
        assert row["price_amount"] == 3500
        assert row["price_display"] == "AED 3,500 / month"

    def test_price_hidden_when_partner_does_not_disclose(self):
        row = build_listing_row(_listing(), price_disclosed=False)
        assert row["price_amount"] is None
        assert row["price_display"] == C.PRICE_HIDDEN_DISPLAY

    def test_hiding_applies_even_to_a_zero_price(self):
        row = build_listing_row(_listing(price_amount=0), price_disclosed=False)
        assert row["price_amount"] is None
        assert row["price_display"] == C.PRICE_HIDDEN_DISPLAY

    def test_labels_are_resolved(self):
        row = build_listing_row(_listing(unit_type="shared_twin"), price_disclosed=True)
        assert row["unit_type_label"] == "Shared / Twin Room"
        assert row["availability_label"] == "Available"

    def test_filter_attributes_pass_through(self):
        row = build_listing_row(_listing(), price_disclosed=True)
        assert row["bedrooms"] == 1
        assert row["bathrooms"] == 1
        assert row["living_rooms"] == 0
        assert row["area_sqft"] == 480
        assert row["lead_count"] == 7

    def test_spots_available_computed_when_column_absent(self):
        listing = _listing(occupancy_max=4, occupants_current=1)
        listing.pop("spots_available")
        row = build_listing_row(listing, price_disclosed=True)
        assert row["spots_available"] == 3

    def test_spots_available_is_none_when_occupancy_unknown(self):
        listing = _listing(occupancy_max=None, occupants_current=None)
        listing.pop("spots_available")
        row = build_listing_row(listing, price_disclosed=True)
        assert row["spots_available"] is None

    def test_price_display_keeps_decimals_when_present(self):
        row = build_listing_row(_listing(price_amount=3499.5), price_disclosed=True)
        assert row["price_display"] == "AED 3,499.50 / month"


# ================================
# STUDENT LEAD ACTIONS
# ================================

class TestLeadActionFlags:
    def test_can_withdraw_only_while_open(self):
        # 'acknowledged' is live, not closed: the partner has read the student's
        # details, which is exactly when withdrawing consent matters most.
        for status in ("submitted", "posted_to_dashboard", "acknowledged", "aging"):
            assert compute_can_withdraw(status) is True
        for status in C.TERMINAL_STATUSES:
            assert compute_can_withdraw(status) is False

    def test_can_withdraw_matches_what_withdraw_actually_accepts(self):
        """
        The flag the client renders a button from and the guard the endpoint
        enforces must agree. They read different sets — can_withdraw asks
        OPEN_STATUSES, withdraw() rejects TERMINAL_STATUSES — so any status
        missing from both made the API advertise one rule and apply another.
        """
        for status in C.LEAD_STATUS_LABELS:
            withdraw_would_succeed = status not in C.TERMINAL_STATUSES
            assert compute_can_withdraw(status) is withdraw_would_succeed, status

    def test_can_fallback_requires_an_eligible_status(self):
        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        assert compute_can_fallback("posted_to_dashboard", old, aging_days=7) is True
        assert compute_can_fallback("aging", old, aging_days=7) is True
        assert compute_can_fallback("acknowledged", old, aging_days=7) is False
        assert compute_can_fallback("withdrawn", old, aging_days=7) is False

    def test_can_fallback_requires_the_lead_to_be_old_enough(self):
        recent = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        assert compute_can_fallback("posted_to_dashboard", recent, aging_days=7) is False

    def test_can_fallback_is_exactly_at_the_threshold(self):
        boundary = (datetime.now(timezone.utc) - timedelta(days=7, minutes=1)).isoformat()
        assert compute_can_fallback("posted_to_dashboard", boundary, aging_days=7) is True

    def test_can_fallback_does_not_wait_for_the_aging_status(self):
        """
        The dashboard backend's daily job sets status='aging'. Eligibility must not
        depend on that job having run, so a still-'posted_to_dashboard' lead older
        than the threshold is reroutable.
        """
        old = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
        assert compute_can_fallback("posted_to_dashboard", old, aging_days=7) is True

    def test_can_fallback_false_without_a_timestamp(self):
        assert compute_can_fallback("posted_to_dashboard", None, aging_days=7) is False

    def test_lead_row_maps_status_labels(self):
        row = build_lead_row(
            {
                "id": "lead-1",
                "lead_reference": "BAITNA-NES-260819-0042",
                "status": "posted_to_dashboard",
                "submitted_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                "acknowledged_at": None,
                "baitna_partners": {"name": "Nescapmus", "property_name": "Campus-1"},
                "baitna_listings": {"unit_type": "studio"},
            }
        )
        assert row["status_label"] == "Awaiting Response"
        assert row["unit_type_label"] == "Studio"
        assert row["partner_name"] == "Nescapmus"
        assert row["can_withdraw"] is True
        assert row["can_fallback"] is False  # only one day old

    def test_every_status_has_a_label(self):
        statuses = {
            "submitted", "posted_to_dashboard", "acknowledged", "aging",
            "converted", "routed", "withdrawn", "closed_no_match", "expired_stale",
        }
        assert statuses == set(C.LEAD_STATUS_LABELS)


# ================================
# SUBMISSION ERROR MAPPING
# ================================

class _PgError(Exception):
    def __init__(self, code, message="", details=""):
        super().__init__(message or code)
        self.code = code
        self.message = message
        self.details = details


class TestCreateErrorMapping:
    def test_open_inquiry_maps_to_409(self):
        err = BaitnaService._translate_create_error(_PgError(C.SQLSTATE_OPEN_INQUIRY))
        assert err.status_code == 409
        assert err.code == C.CODE_OPEN_INQUIRY_EXISTS
        assert "already have an open inquiry" in err.message

    def test_cooldown_maps_to_409_and_carries_the_eligible_date(self):
        err = BaitnaService._translate_create_error(
            _PgError(
                C.SQLSTATE_COOLDOWN,
                message="You submitted an inquiry to this partner recently. "
                        "You can submit again after 2026-10-04.",
                details="2026-10-04",
            )
        )
        assert err.status_code == 409
        assert err.code == C.CODE_COOLDOWN_ACTIVE
        assert err.data == {"eligible_from": "2026-10-04"}

    def test_inactive_partner_maps_to_404(self):
        err = BaitnaService._translate_create_error(_PgError(C.SQLSTATE_PARTNER_INACTIVE))
        assert err.status_code == 404
        assert err.code == C.CODE_PARTNER_NOT_FOUND
        assert err.message == "Partner or listing not found or not currently active."

    def test_the_two_conflicts_are_distinguishable(self):
        """Both are 409s; only `code` tells the mobile app which rule fired."""
        a = BaitnaService._translate_create_error(_PgError(C.SQLSTATE_OPEN_INQUIRY))
        b = BaitnaService._translate_create_error(_PgError(C.SQLSTATE_COOLDOWN))
        assert a.status_code == b.status_code == 409
        assert a.code != b.code

    def test_missing_student_maps_to_401(self):
        err = BaitnaService._translate_create_error(_PgError(C.SQLSTATE_STUDENT_NOT_FOUND))
        assert err.status_code == 401
        assert err.code == C.CODE_STUDENT_NOT_FOUND

    def test_unknown_error_maps_to_500(self):
        err = BaitnaService._translate_create_error(_PgError("42P01", "relation missing"))
        assert err.status_code == 500
        assert err.code == C.CODE_INTERNAL

    def test_sqlstate_recovered_from_the_string_form(self):
        """Older clients don't expose .code; the BT0xx codes still have to land."""
        plain = Exception("error running query: BT001 open inquiry")
        err = BaitnaService._translate_create_error(plain)
        assert err.code == C.CODE_OPEN_INQUIRY_EXISTS


# ================================
# BROWSE FEED
# ================================

class TestConcurrentSubmitRace:
    """
    The IF EXISTS guard inside baitna_create_lead is not atomic with the insert,
    so a double-tapped submit button puts two inserts in flight and the partial
    unique index rejects the loser. That is the same conflict BT001 names, and it
    must read as one to the client rather than a 500 they would simply retry.
    """

    def test_unique_violation_is_the_open_inquiry_conflict(self):
        err = BaitnaService._translate_create_error(
            _PgError(
                "23505",
                'duplicate key value violates unique constraint '
                '"baitna_leads_one_open_per_student_partner"',
            )
        )
        assert err.status_code == 409
        assert err.code == C.CODE_OPEN_INQUIRY_EXISTS

    def test_it_matches_the_index_the_migration_creates(self):
        sql = TestEnumsAgree.MIGRATION.read_text(encoding="utf-8")
        assert C.OPEN_INQUIRY_INDEX in sql

    def test_an_unexpected_unique_violation_still_answers_cleanly(self):
        """Any other 23505 on this path is still a conflict, not a server fault."""
        err = BaitnaService._translate_create_error(
            _PgError("23505", "duplicate key value violates unique constraint \"whatever\"")
        )
        assert err.status_code == 409


class TestBrowseFilters:
    def _run(self, service, monkeypatch, filters, rows=None, count=0):
        query = FakeQuery(rows=rows or [], count=count)
        monkeypatch.setattr(
            "app.modules.baitna.service.get_supabase_client",
            lambda: FakeSupabase(query),
        )
        result = service.browse_listings(filters)
        return query, result

    def test_only_active_listings_and_partners(self, service, monkeypatch):
        query, _ = self._run(service, monkeypatch, StubFilters())
        assert query.has_filter("eq", "is_active", True)
        assert query.has_filter("eq", "baitna_partners.is_active", True)

    def test_availability_defaults_to_available_and_limited(self, service, monkeypatch):
        query, _ = self._run(service, monkeypatch, StubFilters())
        args, _kwargs = query.filters("in_")[0]
        assert args[0] == "availability_status"
        assert set(args[1]) == {"available", "limited"}

    def test_room_filters_emit_gte_predicates(self, service, monkeypatch):
        query, _ = self._run(
            service,
            monkeypatch,
            StubFilters(bedrooms_min=2, bathrooms_min=2, living_rooms_min=1),
        )
        assert query.has_filter("gte", "bedrooms", 2)
        assert query.has_filter("gte", "bathrooms", 2)
        assert query.has_filter("gte", "living_rooms", 1)

    def test_area_range_emits_both_bounds(self, service, monkeypatch):
        query, _ = self._run(
            service, monkeypatch, StubFilters(area_sqft_min=600, area_sqft_max=1200)
        )
        assert query.has_filter("gte", "area_sqft", 600)
        assert query.has_filter("lte", "area_sqft", 1200)

    def test_has_spots_available_filters_the_generated_column(self, service, monkeypatch):
        query, _ = self._run(service, monkeypatch, StubFilters(has_spots_available=True))
        assert query.has_filter("gt", "spots_available", 0)

    def test_unit_type_filter_is_an_in_clause(self, service, monkeypatch):
        query, _ = self._run(
            service, monkeypatch, StubFilters(unit_type=["studio", "one_bed"])
        )
        assert query.has_filter("in_", "unit_type", ["studio", "one_bed"])

    def test_pagination_range_is_zero_indexed(self, service, monkeypatch):
        query, result = self._run(
            service, monkeypatch, StubFilters(page=3, page_size=20), count=47
        )
        args, _ = query.filters("range")[0]
        assert args == (40, 59)
        assert result["page"] == 3
        assert result["total"] == 47

    def test_total_reflects_the_filtered_count(self, service, monkeypatch):
        _, result = self._run(
            service, monkeypatch, StubFilters(bedrooms_min=2), count=4
        )
        assert result["total"] == 4

    def test_rows_carry_their_partner_inline(self, service, monkeypatch):
        row = _listing()
        row["baitna_partners"] = {
            "id": "partner-1",
            "name": "Azizi Developments",
            "property_name": "Azizi Riviera",
            "logo_url": "https://example.com/logo.png",
            "price_disclosure_enabled": True,
        }
        _, result = self._run(service, monkeypatch, StubFilters(), rows=[row], count=1)
        listing = result["listings"][0]
        assert listing["partner_name"] == "Azizi Developments"
        assert listing["property_name"] == "Azizi Riviera"
        assert listing["price_amount"] == 3500

    def test_browse_rows_respect_price_disclosure(self, service, monkeypatch):
        row = _listing()
        row["baitna_partners"] = {
            "id": "partner-1",
            "name": "Quiet Partner",
            "price_disclosure_enabled": False,
        }
        _, result = self._run(service, monkeypatch, StubFilters(), rows=[row], count=1)
        listing = result["listings"][0]
        assert listing["price_amount"] is None
        assert listing["price_display"] == C.PRICE_HIDDEN_DISPLAY


class TestPriceDisclosureLeakGuard:
    """
    A student must not be able to work out a price the partner chose to hide.
    Both routes to that — narrowing a price range until a listing appears, and
    reading its position in a price-sorted list — go through price_sort, which is
    NULL for partners with disclosure switched off.
    """

    def _query_for(self, service, monkeypatch, filters):
        query = FakeQuery()
        monkeypatch.setattr(
            "app.modules.baitna.service.get_supabase_client",
            lambda: FakeSupabase(query),
        )
        service.browse_listings(filters)
        return query

    def test_price_filters_run_against_price_sort(self, service, monkeypatch):
        query = self._query_for(
            service, monkeypatch, StubFilters(price_min=3000, price_max=5000)
        )
        assert query.has_filter("gte", "price_sort", 3000)
        assert query.has_filter("lte", "price_sort", 5000)
        # Never the raw column — that would match hidden-price listings.
        assert not query.has_filter("gte", "price_amount")
        assert not query.has_filter("lte", "price_amount")

    def test_price_sort_orders_by_price_sort(self, service, monkeypatch):
        query = self._query_for(service, monkeypatch, StubFilters(sort="price", order="asc"))
        assert query.order_param().startswith("price_sort.asc")

    def test_hidden_prices_sort_last_in_both_directions(self, service, monkeypatch):
        """
        Asserted on the emitted parameter, not on the arguments handed to the
        builder. postgrest-py's order() only ever writes `.nullsfirst`; there is
        no nullslast option, so nullsfirst=False emitted nothing and Postgres'
        own default took over — NULLS FIRST for DESC. The earlier version of this
        test checked that we passed nullsfirst=False and so passed while every
        hidden price sorted to the top of the default price view.
        """
        for order in ("asc", "desc"):
            query = self._query_for(
                service, monkeypatch, StubFilters(sort="price", order=order)
            )
            first = query.order_param().split(",")[0]
            assert first == f"price_sort.{order}.nullslast", first

    def test_every_sort_pins_nulls_last_in_both_directions(self, service, monkeypatch):
        """Nullable sort columns (price_sort, bedrooms, area_sqft) must never lead
        the feed with the rows that have no value."""
        for key in C.LISTING_SORTS:
            for order in ("asc", "desc"):
                query = self._query_for(
                    service, monkeypatch, StubFilters(sort=key, order=order)
                )
                for term in query.order_param().split(","):
                    assert term.endswith(".nullslast"), (key, order, term)

    def test_we_do_not_rely_on_the_builders_nullsfirst_flag(self):
        """
        Pins the library behaviour this works around, so an upgrade that changes
        it is noticed here rather than through a reordered feed in production.
        """
        from postgrest import SyncPostgrestClient

        client = SyncPostgrestClient("http://localhost/rest/v1", schema="public", headers={})
        emitted = (
            client.table("t").select("*")
            .order("price_sort", desc=True, nullsfirst=False)
            .params.get("order")
        )
        assert "nullslast" not in emitted, (
            "postgrest now emits nullslast; _apply_sort can stop writing the "
            "order parameter by hand"
        )


class TestBrowseSorting:
    def _query_for(self, service, monkeypatch, filters):
        query = FakeQuery()
        monkeypatch.setattr(
            "app.modules.baitna.service.get_supabase_client",
            lambda: FakeSupabase(query),
        )
        service.browse_listings(filters)
        return query

    def test_popularity_sorts_by_lead_count(self, service, monkeypatch):
        query = self._query_for(service, monkeypatch, StubFilters(sort="popularity"))
        assert query.order_param().startswith("lead_count.")

    def test_every_sort_key_maps_to_a_column(self, service, monkeypatch):
        for key in C.LISTING_SORTS:
            query = self._query_for(service, monkeypatch, StubFilters(sort=key))
            order = query.order_param()
            assert order, f"{key} produced no ordering"
            assert order.split(".")[0] == C.LISTING_SORTS[key], key

    def test_created_at_breaks_ties_without_repeating_itself(self, service, monkeypatch):
        """Paging needs a stable tiebreaker, but sort=newest is already ordered by
        created_at and must not name it twice."""
        query = self._query_for(service, monkeypatch, StubFilters(sort="popularity"))
        assert query.order_param().split(",")[1].startswith("created_at.desc")

        query = self._query_for(service, monkeypatch, StubFilters(sort="newest"))
        assert query.order_param().count("created_at") == 1

    def test_created_at_is_the_stable_tiebreaker(self, service, monkeypatch):
        """Without a deterministic tiebreaker, paging repeats and skips rows."""
        query = self._query_for(service, monkeypatch, StubFilters(sort="bedrooms"))
        assert query.order_param().split(",")[-1].startswith("created_at.")


class TestPageSizeClamping:
    def test_oversized_page_size_clamps(self):
        assert resolve_page_size(500, default=20, maximum=50) == 50

    def test_absent_page_size_uses_the_default(self):
        assert resolve_page_size(None, default=20, maximum=50) == 20

    def test_reasonable_page_size_passes_through(self):
        assert resolve_page_size(10, default=20, maximum=50) == 10


# ================================
# FALLBACK MATCHING
# ================================

class TestFallbackCandidate:
    def _service_with(self, service, monkeypatch, listings, blocked=None):
        query = FakeQuery(rows=listings)
        monkeypatch.setattr(
            "app.modules.baitna.service.get_supabase_client",
            lambda: FakeSupabase(query),
        )
        monkeypatch.setattr(
            BaitnaService, "_blocked_partner_ids", lambda self, sid: set(blocked or [])
        )
        return query

    def test_picks_the_first_unblocked_partner(self, service, monkeypatch):
        rows = [
            _listing(id="l1", partner_id="p-blocked"),
            _listing(id="l2", partner_id="p-open"),
        ]
        self._service_with(service, monkeypatch, rows, blocked={"p-blocked"})
        found = service._find_fallback_candidate("student-1", "studio", None)
        assert found["id"] == "l2"

    def test_excludes_the_original_partner(self, service, monkeypatch):
        rows = [_listing(id="l1", partner_id="p-original")]
        self._service_with(service, monkeypatch, rows)
        found = service._find_fallback_candidate("student-1", "studio", "p-original")
        assert found is None

    def test_queries_only_matching_unit_type_and_real_availability(self, service, monkeypatch):
        query = self._service_with(service, monkeypatch, [])
        service._find_fallback_candidate("student-1", "one_bed", None)
        assert query.has_filter("eq", "unit_type", "one_bed")
        args, _ = query.filters("in_")[0]
        assert args[0] == "availability_status"
        assert set(args[1]) == {"available", "limited"}

    def test_only_active_listings_and_partners(self, service, monkeypatch):
        query = self._service_with(service, monkeypatch, [])
        service._find_fallback_candidate("student-1", "studio", None)
        assert query.has_filter("eq", "is_active", True)
        assert query.has_filter("eq", "baitna_partners.is_active", True)

    def test_blocked_partners_are_excluded_in_the_query(self, service, monkeypatch):
        """Filtering server-side keeps this a small read as the catalogue grows."""
        query = self._service_with(service, monkeypatch, [], blocked={"p-blocked"})
        service._find_fallback_candidate("student-1", "studio", "p-original")
        args, _ = query.filters("not_in_")[0]
        assert args[0] == "partner_id"
        assert set(args[1]) == {"p-blocked", "p-original"}

    def test_the_scan_is_bounded(self, service, monkeypatch):
        query = self._service_with(service, monkeypatch, [])
        service._find_fallback_candidate("student-1", "studio", None)
        assert query.filters("limit"), "fallback lookup must not fetch unbounded rows"

    def test_no_unit_type_means_no_match(self, service, monkeypatch):
        assert service._find_fallback_candidate("student-1", None, None) is None

    def test_empty_result_returns_none(self, service, monkeypatch):
        self._service_with(service, monkeypatch, [])
        assert service._find_fallback_candidate("student-1", "studio", None) is None


class TestBlockedPartners:
    def _with_leads(self, service, monkeypatch, leads):
        query = FakeQuery(rows=leads)
        monkeypatch.setattr(
            "app.modules.baitna.service.get_supabase_client",
            lambda: FakeSupabase(query),
        )

    def test_open_lead_blocks_its_partner(self, service, monkeypatch):
        self._with_leads(
            service, monkeypatch,
            [{"partner_id": "p1", "status": "posted_to_dashboard", "closed_at": None}],
        )
        assert service._blocked_partner_ids("student-1") == {"p1"}

    def test_recently_closed_lead_blocks_its_partner(self, service, monkeypatch):
        recent = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        self._with_leads(
            service, monkeypatch,
            [{"partner_id": "p1", "status": "withdrawn", "closed_at": recent}],
        )
        assert service._blocked_partner_ids("student-1") == {"p1"}

    def test_acknowledged_lead_blocks_the_partner(self, service, monkeypatch):
        """An acknowledged lead is live, so a second inquiry to that partner —
        direct or via a reroute landing there — must not be possible."""
        self._with_leads(
            service, monkeypatch,
            [{"partner_id": "p1", "status": "acknowledged", "closed_at": None}],
        )
        assert service._blocked_partner_ids("student-1") == {"p1"}

    def test_every_open_status_blocks_the_partner(self, service, monkeypatch):
        for status in C.OPEN_STATUSES:
            self._with_leads(
                service, monkeypatch,
                [{"partner_id": "p1", "status": status, "closed_at": None}],
            )
            assert service._blocked_partner_ids("student-1") == {"p1"}, status

    def test_long_closed_lead_does_not_block(self, service, monkeypatch):
        old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        self._with_leads(
            service, monkeypatch,
            [{"partner_id": "p1", "status": "withdrawn", "closed_at": old}],
        )
        assert service._blocked_partner_ids("student-1") == set()


# ================================
# CONSENT CARRIED ACROSS A REROUTE
# ================================

class TestConsentEventLookup:
    """
    A reroute copies the original consent forward. consent_text_snapshot is the
    legal record, and the column is only NOT NULL — an empty string satisfies it —
    so every failure here has to raise rather than hand back a blank snapshot.
    """

    def _with(self, monkeypatch, rows=None, raises=False):
        query = FakeQuery(rows=rows or [])
        if raises:
            def boom():
                raise RuntimeError("postgrest is down")
            query.execute = boom
        monkeypatch.setattr(
            "app.modules.baitna.service.get_supabase_client",
            lambda: FakeSupabase(query),
        )

    def test_missing_consent_event_id_raises(self, service, monkeypatch):
        with pytest.raises(BaitnaError) as exc:
            service._get_consent_event(None)
        assert exc.value.status_code == 500

    def test_read_failure_raises_instead_of_returning_empty(self, service, monkeypatch):
        self._with(monkeypatch, raises=True)
        with pytest.raises(BaitnaError) as exc:
            service._get_consent_event("consent-1")
        assert exc.value.status_code == 500

    def test_absent_row_raises(self, service, monkeypatch):
        self._with(monkeypatch, rows=[])
        with pytest.raises(BaitnaError):
            service._get_consent_event("consent-1")

    def test_blank_snapshot_raises(self, service, monkeypatch):
        self._with(monkeypatch, rows=[{"consent_text_snapshot": "   "}])
        with pytest.raises(BaitnaError):
            service._get_consent_event("consent-1")

    def test_good_record_is_returned(self, service, monkeypatch):
        self._with(monkeypatch, rows=[{"consent_text_snapshot": "as shown to me",
                                       "consent_version": "baitna_v1"}])
        assert service._get_consent_event("consent-1")["consent_version"] == "baitna_v1"


class TestResendGuard:
    """
    The confirmation email says the inquiry is with the partner and a reply is
    coming. Resending that for a closed lead is misleading, and for a withdrawn
    one it contradicts the consent the student just revoked.
    """

    def _lead(self, service, monkeypatch, status):
        monkeypatch.setattr(
            BaitnaService, "get_own_lead",
            lambda self, sid, lid, s=status: {"id": lid, "status": s},
        )

    def test_open_leads_are_resendable(self, service, monkeypatch):
        for status in C.OPEN_STATUSES:
            self._lead(service, monkeypatch, status)
            assert service.get_resendable_lead("student-1", "lead-1")["status"] == status

    def test_closed_leads_are_refused(self, service, monkeypatch):
        for status in C.TERMINAL_STATUSES:
            self._lead(service, monkeypatch, status)
            with pytest.raises(BaitnaError) as exc:
                service.get_resendable_lead("student-1", "lead-1")
            assert exc.value.status_code == 409, status
            assert exc.value.code == C.CODE_ALREADY_CLOSED, status

    def test_a_withdrawn_lead_is_refused(self, service, monkeypatch):
        self._lead(service, monkeypatch, "withdrawn")
        with pytest.raises(BaitnaError) as exc:
            service.get_resendable_lead("student-1", "lead-1")
        assert exc.value.code == C.CODE_ALREADY_CLOSED


# ================================
# WITHDRAWAL
# ================================

class TestWithdraw:
    def test_terminal_lead_cannot_be_withdrawn_again(self, service, monkeypatch):
        monkeypatch.setattr(
            BaitnaService,
            "get_own_lead",
            lambda self, sid, lid: {"id": lid, "status": "withdrawn"},
        )
        with pytest.raises(BaitnaError) as exc:
            service.withdraw("student-1", "lead-1", None)
        assert exc.value.status_code == 409
        assert exc.value.code == C.CODE_ALREADY_CLOSED

    def test_every_terminal_status_is_rejected(self, service, monkeypatch):
        for status in C.TERMINAL_STATUSES:
            monkeypatch.setattr(
                BaitnaService,
                "get_own_lead",
                lambda self, sid, lid, s=status: {"id": lid, "status": s},
            )
            with pytest.raises(BaitnaError):
                service.withdraw("student-1", "lead-1", None)

    def test_acknowledged_lead_can_be_withdrawn(self, service, monkeypatch):
        """can_withdraw reports true for acknowledged, so the endpoint must honour it."""
        query = FakeQuery()
        monkeypatch.setattr(
            "app.modules.baitna.service.get_supabase_client",
            lambda: FakeSupabase(query),
        )
        monkeypatch.setattr(
            BaitnaService,
            "get_own_lead",
            lambda self, sid, lid: {
                "id": lid,
                "status": "acknowledged",
                "lead_reference": "BAITNA-NES-260819-0042",
                "consent_event_id": "consent-1",
            },
        )
        updates = []
        monkeypatch.setattr(
            BaitnaService, "_set_lead_status",
            lambda self, lid, status: updates.append((lid, status)),
        )

        result = service.withdraw("student-1", "lead-1", None)

        assert result["status"] == "withdrawn"
        assert updates == [("lead-1", "withdrawn")]

    def test_open_lead_is_withdrawn_and_consent_revoked(self, service, monkeypatch):
        query = FakeQuery()
        monkeypatch.setattr(
            "app.modules.baitna.service.get_supabase_client",
            lambda: FakeSupabase(query),
        )
        monkeypatch.setattr(
            BaitnaService,
            "get_own_lead",
            lambda self, sid, lid: {
                "id": lid,
                "status": "posted_to_dashboard",
                "lead_reference": "BAITNA-NES-260819-0042",
                "consent_event_id": "consent-1",
            },
        )
        updates = []
        monkeypatch.setattr(
            BaitnaService,
            "_set_lead_status",
            lambda self, lid, status: updates.append((lid, status)),
        )

        result = service.withdraw("student-1", "lead-1", "Changed my mind")

        assert result["status"] == "withdrawn"
        assert result["lead_reference"] == "BAITNA-NES-260819-0042"
        assert updates == [("lead-1", "withdrawn")]
        # closed_at is stamped by the database trigger, never by the service.
        assert "closed_at" not in result


# ================================
# ENUM DEFINITIONS STAY IN SYNC
# ================================

class TestEnumsAgree:
    """
    Every Baitna enum is written down three times: as a label map or set in
    constants.py, as a Literal in schemas.py, and as a CHECK constraint in the
    migration. Literals have to be static, so the duplication can't be removed —
    but drift can be caught. Without these, adding a sixth unit_type to the
    database and forgetting the Literal produces a 422 on a value the database
    happily accepts.
    """

    MIGRATION = (
        Path(__file__).resolve().parents[2]
        / "migrations" / "versions" / "20260904_add_baitna.sql"
    )

    @classmethod
    def sql_check_values(cls, column: str) -> set:
        """Pull the value list out of `<column> ... CHECK (<column> IN (...))`."""
        sql = cls.MIGRATION.read_text(encoding="utf-8")
        # `IN` and its value list are wrapped across lines for some columns, so
        # both gaps have to tolerate newlines.
        match = re.search(
            rf"CHECK \(\s*{column}\s+IN\s*\(([^)]*)\)", sql, re.S
        )
        assert match, f"no CHECK constraint found for {column}"
        return set(re.findall(r"'([a-z_0-9]+)'", match.group(1)))

    def test_unit_types_agree(self):
        assert set(C.UNIT_TYPE_LABELS) == set(get_args(UnitType))
        assert set(C.UNIT_TYPE_LABELS) == self.sql_check_values("unit_type")

    def test_availability_values_agree(self):
        assert set(C.AVAILABILITY_LABELS) == set(get_args(AvailabilityStatus))
        assert set(C.AVAILABILITY_LABELS) == self.sql_check_values("availability_status")

    def test_budget_bands_agree(self):
        assert set(get_args(BudgetBand)) == self.sql_check_values("budget_band")

    def test_current_statuses_agree(self):
        assert set(get_args(CurrentStatus)) == self.sql_check_values("current_status")

    def test_lead_statuses_agree(self):
        assert set(C.LEAD_STATUS_LABELS) == self.sql_check_values("status")

    def test_sort_keys_agree(self):
        assert set(C.LISTING_SORTS) == set(get_args(ListingSort))

    def test_open_and_terminal_statuses_are_known_and_disjoint(self):
        known = set(C.LEAD_STATUS_LABELS)
        assert C.OPEN_STATUSES <= known
        assert C.TERMINAL_STATUSES <= known
        assert not (C.OPEN_STATUSES & C.TERMINAL_STATUSES)

    def test_open_and_terminal_statuses_cover_every_status(self):
        """
        The two sets must partition the statuses, not merely stay disjoint.
        Anything in neither is read as closed by can_withdraw and as open by
        withdraw(), which is how 'acknowledged' came to advertise no withdraw
        button on a lead the endpoint would happily withdraw.
        """
        assert C.OPEN_STATUSES | C.TERMINAL_STATUSES == set(C.LEAD_STATUS_LABELS)

    def test_open_statuses_match_the_sql(self):
        """
        OPEN_STATUSES is written down three times: here, in the partial unique
        index, and in the BT001 guard inside baitna_create_lead. If the SQL is
        narrower, the database lets a student open a second lead with a partner
        the service already considers blocked.
        """
        sql = self.MIGRATION.read_text(encoding="utf-8")

        index = re.search(
            r"CREATE UNIQUE INDEX baitna_leads_one_open_per_student_partner"
            r".*?WHERE status IN \(([^)]*)\)",
            sql, re.S,
        )
        assert index, "one-open-per-partner index not found"
        assert set(re.findall(r"'([a-z_]+)'", index.group(1))) == set(C.OPEN_STATUSES)

        guard = re.search(
            r"AND partner_id = p_partner_id.*?AND status IN \(([^)]*)\)",
            sql, re.S,
        )
        assert guard, "BT001 open-inquiry guard not found"
        assert set(re.findall(r"'([a-z_]+)'", guard.group(1))) == set(C.OPEN_STATUSES)

    def test_cooldown_setting_matches_the_trigger(self):
        """
        BAITNA_LEAD_COOLDOWN_DAYS decides which partners a reroute may target,
        while baitna_leads_enforce_floor hardcodes the interval the database
        actually enforces. If the setting is the shorter of the two, the service
        offers a partner the insert then rejects with BT002.
        """
        from app.core.config import Settings

        sql = self.MIGRATION.read_text(encoding="utf-8")
        intervals = set(re.findall(r"interval '(\d+) days'", sql))
        assert intervals, "no cooldown interval found in the floor trigger"
        assert intervals == {str(Settings().BAITNA_LEAD_COOLDOWN_DAYS)}, intervals

    def test_every_view_is_revoked_from_the_anon_key(self):
        """
        RLS does not reach through a view: it runs with its owner's rights unless
        security_invoker is set, and that owner bypasses the base tables' RLS.
        Supabase grants SELECT on new objects in public to anon by default, so a
        view over student contact details is readable with the key that ships in
        the mobile app unless it is explicitly revoked.
        """
        sql = self.MIGRATION.read_text(encoding="utf-8")
        views = re.findall(r"CREATE (?:OR REPLACE )?VIEW (\w+)", sql)
        assert views, "no views found; drop this test if the view was removed"
        for view in views:
            assert re.search(rf"REVOKE ALL ON {view} FROM[^;]*anon", sql), view
            assert f"security_invoker = on" in sql, view

    def test_the_view_does_not_read_a_full_name_column(self):
        """
        public.users has `name`, not `full_name`. Selecting the wrong one makes
        CREATE VIEW fail and aborts the migration part-way through, after the
        tables and triggers have already been created.
        """
        sql = self.MIGRATION.read_text(encoding="utf-8")
        assert "u.full_name" not in sql
        assert "u.name" in sql

    def test_fallback_sets_are_subsets(self):
        assert C.FALLBACK_ELIGIBLE_STATUSES <= set(C.LEAD_STATUS_LABELS)
        assert C.BOOKABLE_AVAILABILITY <= set(C.AVAILABILITY_LABELS)

    def test_price_sorts_on_the_redacted_column(self):
        """
        The one sort key whose column name differs from its public name. If this
        ever maps back to price_amount, hidden prices become inferable from where
        a listing lands in a price-sorted page.
        """
        assert C.LISTING_SORTS["price"] == "price_sort"


# ================================
# MOVE-IN DATE
# ================================

class TestMoveInDate:
    """
    Neither pydantic's `date` type nor the database restricts which dates are
    sensible, so a mistyped year used to reach the partner as a real inquiry
    reading "Desired Move-in: January 2020".
    """

    UUID = "22222222-2222-2222-2222-222222222222"

    def _body(self, move_in):
        return {
            "partner_id": self.UUID,
            "listing_id": self.UUID,
            "move_in_date": move_in,
            "lease_length_months": 12,
            "budget_band": "3500_5000",
            "current_status": "arriving_soon",
            "consent": {
                "consent_version": "baitna_v1",
                "consent_text_snapshot": "I consent ...",
            },
        }

    @property
    def today(self):
        return datetime.now(C.DUBAI_TZ).date()

    def test_today_is_accepted(self):
        assert LeadCreateRequest(**self._body(self.today)).move_in_date == self.today

    def test_near_future_is_accepted(self):
        target = self.today + timedelta(days=30)
        assert LeadCreateRequest(**self._body(target)).move_in_date == target

    def test_yesterday_is_rejected(self):
        with pytest.raises(ValidationError) as exc:
            LeadCreateRequest(**self._body(self.today - timedelta(days=1)))
        assert "past" in str(exc.value)

    def test_mistyped_past_year_is_rejected(self):
        with pytest.raises(ValidationError):
            LeadCreateRequest(**self._body("2020-01-01"))

    def test_mistyped_future_year_is_rejected(self):
        with pytest.raises(ValidationError) as exc:
            LeadCreateRequest(**self._body("2062-10-01"))
        assert "far in the future" in str(exc.value)

    def test_horizon_boundary_is_inclusive(self):
        edge = self.today + timedelta(days=C.MOVE_IN_MAX_DAYS)
        assert LeadCreateRequest(**self._body(edge)).move_in_date == edge
        with pytest.raises(ValidationError):
            LeadCreateRequest(**self._body(edge + timedelta(days=1)))

    def test_uses_the_dubai_calendar_day(self):
        """Lead references are issued on the Dubai day; validation must match, or
        a student submitting late evening in Dubai could be told today is past."""
        assert C.DUBAI_TZ.utcoffset(None) == timedelta(hours=4)


# ================================
# REROUTE MOVE-IN DATE
# ================================

class TestRerouteMoveInDate:
    """
    A lead only becomes reroutable after a week of silence, so the original
    move-in date may have passed while the student waited. Carrying it over would
    hand the new partner an inquiry for a date in the past.
    """

    def _lead(self, move_in, status="posted_to_dashboard"):
        return {
            "id": "lead-1",
            "lead_reference": "BAITNA-NES-260819-0042",
            "status": status,
            "submitted_at": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
            "move_in_date": move_in,
            "lease_length_months": 12,
            "budget_band": "3500_5000",
            "current_status": "arriving_soon",
            "partner_id": "p-original",
            "consent_event_id": "consent-1",
            "baitna_listings": {"unit_type": "studio"},
        }

    def _wire(self, service, monkeypatch, lead, captured):
        monkeypatch.setattr(BaitnaService, "get_own_lead", lambda self, s, l: lead)
        monkeypatch.setattr(
            BaitnaService, "_find_fallback_candidate",
            lambda self, student_id, unit_type, exclude_partner_id: {
                "id": "listing-2", "partner_id": "p-new"},
        )
        monkeypatch.setattr(
            BaitnaService, "_get_consent_event",
            lambda self, cid: {"consent_version": "baitna_v1",
                               "consent_text_snapshot": "text"},
        )
        monkeypatch.setattr(BaitnaService, "_set_lead_status", lambda self, l, st: None)

        def fake_create(self, **kwargs):
            captured.update(kwargs)
            return {"id": "lead-2", "lead_reference": "BAITNA-MYR-260829-0001",
                    "partner_name": "Myriad"}

        monkeypatch.setattr(BaitnaService, "_invoke_create_lead", fake_create)

    def test_future_original_date_is_carried_over(self, service, monkeypatch):
        future = (datetime.now(C.DUBAI_TZ).date() + timedelta(days=60)).isoformat()
        captured = {}
        self._wire(service, monkeypatch, self._lead(future), captured)

        payload, _ = service.route_fallback("student-1", "lead-1")

        assert captured["move_in_date"] == future
        assert payload["move_in_date"] == future

    def test_past_original_date_demands_a_new_one(self, service, monkeypatch):
        past = (datetime.now(C.DUBAI_TZ).date() - timedelta(days=3)).isoformat()
        self._wire(service, monkeypatch, self._lead(past), {})

        with pytest.raises(BaitnaError) as exc:
            service.route_fallback("student-1", "lead-1")

        assert exc.value.status_code == 409
        assert exc.value.code == C.CODE_MOVE_IN_DATE_REQUIRED
        assert exc.value.data == {"original_move_in_date": past}

    def test_supplied_date_overrides_a_past_original(self, service, monkeypatch):
        past = (datetime.now(C.DUBAI_TZ).date() - timedelta(days=3)).isoformat()
        chosen = datetime.now(C.DUBAI_TZ).date() + timedelta(days=45)
        captured = {}
        self._wire(service, monkeypatch, self._lead(past), captured)

        payload, _ = service.route_fallback("student-1", "lead-1", move_in_date=chosen)

        assert captured["move_in_date"] == chosen.isoformat()
        assert payload["move_in_date"] == chosen.isoformat()

    def test_supplied_date_also_overrides_a_valid_original(self, service, monkeypatch):
        future = (datetime.now(C.DUBAI_TZ).date() + timedelta(days=10)).isoformat()
        chosen = datetime.now(C.DUBAI_TZ).date() + timedelta(days=90)
        captured = {}
        self._wire(service, monkeypatch, self._lead(future), captured)

        service.route_fallback("student-1", "lead-1", move_in_date=chosen)
        assert captured["move_in_date"] == chosen.isoformat()

    def test_body_is_optional(self):
        assert FallbackRouteRequest().move_in_date is None

    def test_body_date_is_validated_like_a_submission(self):
        with pytest.raises(ValidationError):
            FallbackRouteRequest(move_in_date="2020-01-01")
        with pytest.raises(ValidationError):
            FallbackRouteRequest(move_in_date="2062-01-01")

    def test_eligibility_is_checked_before_the_date(self, service, monkeypatch):
        """A closed lead is rejected as ineligible, not asked for a new date."""
        past = (datetime.now(C.DUBAI_TZ).date() - timedelta(days=3)).isoformat()
        closed = {
            "id": "lead-1",
            "status": "withdrawn",
            "move_in_date": past,
            "submitted_at": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
        }
        monkeypatch.setattr(BaitnaService, "get_own_lead", lambda self, s, l: closed)

        with pytest.raises(BaitnaError) as exc:
            service.route_fallback("student-1", "lead-1")
        assert exc.value.code == C.CODE_NOT_FALLBACK_ELIGIBLE


# ================================
# OWNERSHIP SCOPING
# ================================

class TestGetOwnLead:
    """
    The only thing stopping one student reading another's inquiry. Scoping has to
    be in the query, not applied to the result after it comes back.
    """

    def _wire(self, monkeypatch, rows):
        query = FakeQuery(rows=rows)
        monkeypatch.setattr(
            "app.modules.baitna.service.get_supabase_client",
            lambda: FakeSupabase(query),
        )
        return query

    def test_query_filters_on_student_id(self, service, monkeypatch):
        query = self._wire(monkeypatch, [{"id": "lead-1"}])
        service.get_own_lead("student-1", "22222222-2222-2222-2222-222222222222")
        assert query.has_filter("eq", "student_id", "student-1")
        assert query.has_filter("eq", "id", "22222222-2222-2222-2222-222222222222")

    def test_someone_elses_lead_reads_as_missing(self, service, monkeypatch):
        """The scoped query returns nothing, so it is a 404 and never a 403 —
        a 403 would confirm the lead exists."""
        self._wire(monkeypatch, [])
        with pytest.raises(BaitnaError) as exc:
            service.get_own_lead("student-1", "22222222-2222-2222-2222-222222222222")
        assert exc.value.status_code == 404
        assert exc.value.code == C.CODE_LEAD_NOT_FOUND

    def test_malformed_id_is_a_404_not_a_500(self, service, monkeypatch):
        """A bad uuid would otherwise reach Postgres as a failed cast."""
        self._wire(monkeypatch, [])
        for bad in ["not-a-uuid", "", "123"]:
            with pytest.raises(BaitnaError) as exc:
                service.get_own_lead("student-1", bad)
            assert exc.value.status_code == 404
            assert exc.value.code == C.CODE_LEAD_NOT_FOUND

    def test_lead_list_is_scoped_too(self, service, monkeypatch):
        query = self._wire(monkeypatch, [])
        service.list_student_leads("student-1")
        assert query.has_filter("eq", "student_id", "student-1")


# ================================
# PARTNER TILES
# ================================

class TestListPartners:
    def _run(self, service, monkeypatch, rows):
        query = FakeQuery(rows=rows)
        monkeypatch.setattr(
            "app.modules.baitna.service.get_supabase_client",
            lambda: FakeSupabase(query),
        )
        return query, service.list_partners()

    def test_inactive_listings_are_dropped(self, service, monkeypatch):
        live = _listing(id="live")
        dead = _listing(id="dead")
        live["is_active"], dead["is_active"] = True, False
        _, result = self._run(service, monkeypatch, [{
            "id": "p1", "name": "Nescapmus", "property_name": "Campus-1",
            "price_disclosure_enabled": True,
            "baitna_listings": [live, dead],
        }])
        ids = [l["id"] for l in result["partners"][0]["listings"]]
        assert ids == ["live"]

    def test_only_active_partners_are_requested(self, service, monkeypatch):
        query, _ = self._run(service, monkeypatch, [])
        assert query.has_filter("eq", "is_active", True)

    def test_hidden_price_applies_to_every_listing_of_that_partner(self, service, monkeypatch):
        a, b = _listing(id="a"), _listing(id="b", price_amount=9999)
        a["is_active"] = b["is_active"] = True
        _, result = self._run(service, monkeypatch, [{
            "id": "p1", "name": "Quiet Partner",
            "price_disclosure_enabled": False,
            "baitna_listings": [a, b],
        }])
        for listing in result["partners"][0]["listings"]:
            assert listing["price_amount"] is None
            assert listing["price_display"] == C.PRICE_HIDDEN_DISPLAY


# ================================
# EMAIL GREETING
# ================================

class TestStudentGreeting:
    """
    public.users carries id, email, name, first_name, last_name — and no
    full_name. Reading a column that does not exist ships 'Hi there,' to every
    student, which is exactly what this suite used to assert was correct.
    """

    def test_prefers_first_name(self):
        assert student_greeting({"first_name": "Sarah", "name": "Sarah Al-Mansoori"}) == "Sarah"

    def test_falls_back_to_the_first_word_of_name(self):
        assert student_greeting({"first_name": None, "name": "Sarah Al-Mansoori"}) == "Sarah"

    def test_falls_back_to_there_when_both_are_missing(self):
        assert student_greeting({"email": "s@uni.edu"}) == "there"

    def test_blank_strings_are_treated_as_missing(self):
        assert student_greeting({"first_name": "  ", "name": ""}) == "there"

    def test_a_full_name_column_is_not_consulted(self):
        """There is no full_name on public.users; reading it degrades silently."""
        assert student_greeting({"full_name": "Sarah Al-Mansoori"}) == "there"


# ================================
# STATUS / TILE VISIBILITY
# ================================

class TestTileVisibility:
    def test_tile_hidden_when_no_active_partners(self, service, monkeypatch):
        query = FakeQuery(rows=[], count=0)
        monkeypatch.setattr(
            "app.modules.baitna.service.get_supabase_client",
            lambda: FakeSupabase(query),
        )
        result = service.get_status()
        assert result["active_partner_count"] == 0
        assert result["tile_visible"] is False

    def test_tile_hidden_when_the_database_is_unreachable(self, service, monkeypatch):
        """A public endpoint polled on app launch must degrade, not raise."""
        monkeypatch.setattr(
            "app.modules.baitna.service.get_supabase_client", lambda: None
        )
        result = service.get_status()
        assert result["active_partner_count"] == 0
        assert result["tile_visible"] is False


# ================================
# DISTANCE TO THE STUDENT'S UNIVERSITY
# ================================

class TestHaversine:
    """
    Straight-line distance in kilometres, behind the "x km away from
    <university>" line on a partner tile.
    """

    def test_identical_points_are_zero(self):
        assert haversine_km(25.1007, 55.1626, 25.1007, 55.1626) == 0.0

    def test_one_degree_of_latitude_is_about_111_km(self):
        """A meridian degree is ~111.2 km anywhere on Earth — the cheapest check
        that the formula is not off by a radians/degrees conversion."""
        km = haversine_km(25.0, 55.0, 26.0, 55.0)
        assert 110.5 < km < 111.5

    def test_known_dubai_pair(self):
        """Heriot-Watt Dubai in Knowledge Park to Zayed University in Academic
        City: roughly 25 km across the city."""
        km = haversine_km(25.1007, 55.1626, 25.1263, 55.4185)
        assert 23 < km < 27

    def test_distance_is_symmetric(self):
        there = haversine_km(25.1007, 55.1626, 24.2028, 55.6773)
        back = haversine_km(24.2028, 55.6773, 25.1007, 55.1626)
        assert there == back

    def test_numeric_columns_arriving_as_strings_are_accepted(self):
        """numeric(9,6) comes back from PostgREST as a string, not a float."""
        assert haversine_km("25.0", "55.0", "26.0", "55.0") == haversine_km(
            25.0, 55.0, 26.0, 55.0
        )

    def test_any_missing_coordinate_yields_none(self):
        for args in (
            (None, 55.0, 26.0, 55.0),
            (25.0, None, 26.0, 55.0),
            (25.0, 55.0, None, 55.0),
            (25.0, 55.0, 26.0, None),
        ):
            assert haversine_km(*args) is None

    def test_unusable_coordinate_is_none_not_an_exception(self):
        """A blank or junk value must not take down the whole partner list."""
        assert haversine_km("", 55.0, 26.0, 55.0) is None
        assert haversine_km("not-a-number", 55.0, 26.0, 55.0) is None

    def test_rounded_to_one_decimal(self):
        km = haversine_km(25.0, 55.0, 25.3, 55.3)
        assert km == round(km, 1)


class TestDistanceLabel:
    def test_label_names_the_university(self):
        assert (
            C.format_distance(12.4, "Zayed University (ZU)")
            == "12.4 km away from Zayed University (ZU)"
        )

    def test_whole_numbers_still_show_a_decimal(self):
        assert C.format_distance(3.0, "AUD") == "3.0 km away from AUD"

    def test_no_distance_means_no_label(self):
        assert C.format_distance(None, "AUD") is None

    def test_no_university_means_no_label(self):
        """Better a tile with no line than one ending in 'away from'."""
        assert C.format_distance(3.4, None) is None
        assert C.format_distance(3.4, "") is None


class TestPartnerDistance:
    def _partner(self, **overrides):
        base = {"id": "p1", "latitude": 25.0, "longitude": 55.0}
        base.update(overrides)
        return base

    def test_distance_from_a_partner_to_a_university(self):
        uni = {"name": "AUD", "latitude": 26.0, "longitude": 55.0}
        assert build_partner_distance(self._partner(), uni) is not None

    def test_no_student_university_means_no_distance(self):
        assert build_partner_distance(self._partner(), None) is None

    def test_partner_without_coordinates_has_no_distance(self):
        """Partners go live before their coordinates are filled in; the tile has
        to survive that rather than report 0 km."""
        uni = {"name": "AUD", "latitude": 26.0, "longitude": 55.0}
        assert build_partner_distance(
            self._partner(latitude=None, longitude=None), uni
        ) is None

    def test_university_without_coordinates_has_no_distance(self):
        uni = {"name": "AUD", "latitude": None, "longitude": None}
        assert build_partner_distance(self._partner(), uni) is None


class TestStudentUniversityLookup:
    """
    users.university is free text on the OTP signup path, so the email domain is
    the only reliable handle on which institution a student actually attends.
    """

    class _Seq:
        """Returns a different row set per read, in order."""

        def __init__(self, *batches):
            self.batches = list(batches)
            self.calls = []

        def table(self, name):
            self.calls.append(name)
            return self

        def select(self, *a, **k):
            return self

        def eq(self, *a, **k):
            self.calls.append(("eq",) + a)
            return self

        def ilike(self, *a, **k):
            self.calls.append(("ilike",) + a)
            return self

        def limit(self, *a, **k):
            return self

        def execute(self):
            rows = self.batches.pop(0) if self.batches else []
            return type("Res", (), {"data": rows, "count": len(rows)})()

    def _wire(self, monkeypatch, fake):
        monkeypatch.setattr(
            "app.modules.baitna.service.get_supabase_client", lambda: fake
        )

    def test_domain_is_matched_first(self, service, monkeypatch):
        fake = self._Seq([{"university_name": "Heriot-Watt University Dubai",
                           "domain": "hw.ac.uk",
                           "latitude": 25.1007, "longitude": 55.1626}])
        self._wire(monkeypatch, fake)

        uni = service._student_university(
            {"email": "Sarah@HW.ac.uk", "university": "whatever they typed"}
        )

        # The typed name is ignored: the domain is the reliable handle.
        assert uni["name"] == "Heriot-Watt University Dubai"
        assert ("ilike", "domain", "hw.ac.uk") in fake.calls

    def test_a_domain_stored_with_capitals_still_matches(self, service, monkeypatch):
        """university_domains is unique on lower(domain), so the table may hold
        'HW.ac.uk'. An exact match against the lowercased email domain would miss
        it and silently drop the distance line for everyone at that university."""
        fake = self._Seq([{"university_name": "Heriot-Watt University Dubai",
                           "domain": "HW.ac.uk",
                           "latitude": 25.1007, "longitude": 55.1626}])
        self._wire(monkeypatch, fake)

        uni = service._student_university({"email": "sarah@hw.ac.uk"})

        assert uni is not None
        assert uni["name"] == "Heriot-Watt University Dubai"
        assert any(
            isinstance(c, tuple) and c[0] == "ilike" and c[1] == "domain"
            for c in fake.calls
        ), "the domain lookup should be case-insensitive"

    def test_a_row_that_only_matches_the_like_pattern_is_rejected(self, service, monkeypatch):
        """LIKE reads _ as a single-character wildcard, so 'a_c.edu' would also
        match 'abc.edu'. The returned row has to be confirmed, not trusted."""
        fake = self._Seq([{"university_name": "Somewhere Else",
                           "domain": "abc.edu",
                           "latitude": 25.0, "longitude": 55.0}])
        self._wire(monkeypatch, fake)

        uni = service._student_university({"email": "s@a_c.edu"})

        # No name was given either, so there is nothing left to fall back to.
        assert uni is None

    def test_name_is_the_fallback_when_the_domain_is_unknown(self, service, monkeypatch):
        fake = self._Seq([], [{"university_name": "University of Dubai (UD)",
                               "latitude": 25.1268, "longitude": 55.4145}])
        self._wire(monkeypatch, fake)

        uni = service._student_university(
            {"email": "s@unknown.example", "university": "University of Dubai (UD)"}
        )

        assert uni["name"] == "University of Dubai (UD)"
        assert any(
            isinstance(c, tuple) and c[0] == "ilike" for c in fake.calls
        )

    def test_unknown_university_still_carries_the_typed_name(self, service, monkeypatch):
        """So the label reads correctly the day coordinates are added for it."""
        self._wire(monkeypatch, self._Seq([], []))
        uni = service._student_university(
            {"email": "s@unknown.example", "university": "Some New College"}
        )
        assert uni == {"name": "Some New College", "latitude": None, "longitude": None}

    def test_no_student_means_no_lookup(self, service):
        assert service._student_university(None) is None

    def test_no_email_and_no_university_means_no_lookup(self, service):
        assert service._student_university({"id": "student-1"}) is None

    def test_a_failed_lookup_does_not_break_the_tiles(self, service, monkeypatch):
        """The housing screen must render without the distance line rather than
        500 because a lookup table is unreachable."""

        class Boom:
            def table(self, name):
                raise RuntimeError("postgrest down")

        self._wire(monkeypatch, Boom())
        assert service._student_university({"email": "s@hw.ac.uk"}) is None


class TestPartnerTilesCarryDistance:
    def _row(self, **overrides):
        base = {
            "id": "p1", "name": "Nescapmus", "property_name": "Campus-1",
            "price_disclosure_enabled": True,
            "latitude": 25.0, "longitude": 55.0,
            "baitna_listings": [],
        }
        base.update(overrides)
        return base

    def _run(self, service, monkeypatch, rows, university):
        query = FakeQuery(rows=rows)
        monkeypatch.setattr(
            "app.modules.baitna.service.get_supabase_client",
            lambda: FakeSupabase(query),
        )
        monkeypatch.setattr(
            BaitnaService, "_student_university", lambda self, s: university
        )
        return query, service.list_partners({"email": "s@hw.ac.uk"})

    def _selected(self, query):
        return " ".join(
            str(arg) for args, _ in query.filters("select") for arg in args
        )

    def test_tile_reports_distance_and_label(self, service, monkeypatch):
        uni = {"name": "Heriot-Watt University Dubai",
               "latitude": 26.0, "longitude": 55.0}
        _, result = self._run(service, monkeypatch, [self._row()], uni)

        tile = result["partners"][0]
        assert tile["distance_km"] is not None
        assert tile["distance_label"].endswith("away from Heriot-Watt University Dubai")
        assert tile["distance_label"].startswith(str(tile["distance_km"]))

    def test_coordinates_are_requested_from_the_partners_table(self, service, monkeypatch):
        query, _ = self._run(service, monkeypatch, [], None)
        selected = self._selected(query)
        assert "latitude" in selected and "longitude" in selected

    def test_partner_without_coordinates_reports_none(self, service, monkeypatch):
        uni = {"name": "AUD", "latitude": 26.0, "longitude": 55.0}
        _, result = self._run(
            service, monkeypatch, [self._row(latitude=None, longitude=None)], uni
        )
        tile = result["partners"][0]
        assert tile["distance_km"] is None
        assert tile["distance_label"] is None

    def test_tiles_still_build_without_a_student(self, service, monkeypatch):
        """The student argument is optional, so nothing about the existing tile
        breaks for a caller that does not pass one."""
        query = FakeQuery(rows=[self._row()])
        monkeypatch.setattr(
            "app.modules.baitna.service.get_supabase_client",
            lambda: FakeSupabase(query),
        )
        result = service.list_partners()
        assert result["partners"][0]["distance_km"] is None

    def test_the_university_is_looked_up_once_for_the_whole_page(self, service, monkeypatch):
        seen = []
        query = FakeQuery(rows=[self._row(id="p1"), self._row(id="p2"),
                                self._row(id="p3")])
        monkeypatch.setattr(
            "app.modules.baitna.service.get_supabase_client",
            lambda: FakeSupabase(query),
        )

        def one_lookup(self, student):
            seen.append(student)
            return {"name": "AUD", "latitude": 26.0, "longitude": 55.0}

        monkeypatch.setattr(BaitnaService, "_student_university", one_lookup)
        service.list_partners({"email": "s@aud.edu"})
        assert len(seen) == 1


# ================================
# SWITCHING THE UNIT ON AN OPEN INQUIRY
# ================================

class TestSwitchFlags:
    """What the app uses to draw the button next to Withdraw."""

    def test_offered_while_the_partner_has_not_replied(self):
        for status in C.SWITCH_ELIGIBLE_STATUSES:
            assert compute_can_switch_listing(status, 0, limit=2) is True

    def test_not_offered_once_the_partner_has_acknowledged(self):
        """The partner has read the student's details and started working that
        specific unit, so it is settled."""
        assert compute_can_switch_listing("acknowledged", 0, limit=2) is False

    def test_never_offered_on_a_closed_lead(self):
        """baitna_switch_listing answers BT006 on these, so advertising the
        button would be a promise the endpoint breaks."""
        for status in C.TERMINAL_STATUSES:
            assert compute_can_switch_listing(status, 0, limit=2) is False

    def test_switching_is_narrower_than_withdrawing(self):
        """Both buttons sit on the same row of the same card, but they do not
        appear and disappear together: withdrawing consent has to work at every
        live stage, switching stops once the partner replies. Anything the switch
        button is offered on must still be withdrawable, though — a lead that can
        be moved but not pulled back would be the wrong way round."""
        assert C.SWITCH_ELIGIBLE_STATUSES < C.OPEN_STATUSES
        for status in C.LEAD_STATUS_LABELS:
            if compute_can_switch_listing(status, 0, limit=2):
                assert compute_can_withdraw(status)

    def test_acknowledged_is_the_only_difference(self):
        """If another status ever separates the two buttons, it should be a
        deliberate decision rather than a silent one."""
        assert C.OPEN_STATUSES - C.SWITCH_ELIGIBLE_STATUSES == {"acknowledged"}

    def test_withdraw_is_still_offered_on_an_acknowledged_lead(self):
        """Losing the switch button must not take the withdraw button with it —
        a student whose details have actually been read is the one who most needs
        it."""
        assert compute_can_withdraw("acknowledged") is True

    def test_withdrawn_once_the_quota_is_spent(self):
        assert compute_can_switch_listing("posted_to_dashboard", 2, limit=2) is False

    def test_still_offered_with_one_left(self):
        assert compute_can_switch_listing("posted_to_dashboard", 1, limit=2) is True

    def test_remaining_counts_down(self):
        assert compute_switches_remaining(0, limit=2) == 2
        assert compute_switches_remaining(1, limit=2) == 1
        assert compute_switches_remaining(2, limit=2) == 0

    def test_remaining_never_goes_negative(self):
        """Lowering the quota below what someone already spent must not put a
        minus sign on the button."""
        assert compute_switches_remaining(5, limit=2) == 0

    def test_lead_row_carries_the_switch_fields(self):
        row = build_lead_row(
            {
                "id": "lead-1",
                "lead_reference": "BAITNA-NES-260819-0042",
                "status": "posted_to_dashboard",
                "listing_id": "listing-1",
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "baitna_partners": {"name": "Nescapmus"},
                "baitna_listings": {"unit_type": "studio"},
            },
            switches_used=1,
        )
        assert row["can_switch_listing"] is True
        assert row["switches_remaining"] == 1
        assert row["listing_id"] == "listing-1"

    def test_lead_row_defaults_to_a_full_allowance(self):
        """A caller that does not pass a count must not accidentally hide the
        button."""
        row = build_lead_row({
            "id": "lead-1", "lead_reference": "R", "status": "posted_to_dashboard",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "baitna_partners": {"name": "N"},
            "baitna_listings": {"unit_type": "studio"},
        })
        assert row["can_switch_listing"] is True


class TestSwitchCounts:
    """The per-partner tally behind switches_remaining on the inquiry list."""

    def _wire(self, monkeypatch, rows):
        query = FakeQuery(rows=rows)
        monkeypatch.setattr(
            "app.modules.baitna.service.get_supabase_client",
            lambda: FakeSupabase(query),
        )
        return query

    def test_counts_are_grouped_by_partner(self, service, monkeypatch):
        self._wire(monkeypatch, [
            {"partner_id": "p1"}, {"partner_id": "p1"}, {"partner_id": "p2"},
        ])
        assert service._switch_counts_by_partner("student-1") == {"p1": 2, "p2": 1}

    def test_the_window_is_a_cutoff_not_the_whole_history(self, service, monkeypatch):
        from app.core.config import Settings

        query = self._wire(monkeypatch, [])
        service._switch_counts_by_partner("student-1")

        assert query.filters("gt"), "no switched_at cutoff applied"
        column, cutoff = query.filters("gt")[0][0]
        assert column == "switched_at"
        expected = datetime.now(timezone.utc) - timedelta(
            days=Settings().BAITNA_LISTING_SWITCH_WINDOW_DAYS
        )
        assert abs((datetime.fromisoformat(cutoff) - expected).total_seconds()) < 60

    def test_scoped_to_the_student(self, service, monkeypatch):
        query = self._wire(monkeypatch, [])
        service._switch_counts_by_partner("student-1")
        assert query.has_filter("eq", "student_id", "student-1")

    def test_a_failure_does_not_break_the_inquiry_list(self, service, monkeypatch):
        """The database counts the rows itself and is the authority, so the worst
        an empty tally does is offer a button the endpoint then refuses."""

        class Boom:
            def table(self, name):
                raise RuntimeError("postgrest down")

        monkeypatch.setattr(
            "app.modules.baitna.service.get_supabase_client", lambda: Boom()
        )
        assert service._switch_counts_by_partner("student-1") == {}

    def test_the_lead_list_asks_for_partner_and_listing_ids(self, service, monkeypatch):
        """Without partner_id the per-partner tally cannot be matched to a row."""
        query = self._wire(monkeypatch, [])
        service.list_student_leads("student-1")
        selected = " ".join(
            str(arg) for args, _ in query.filters("select") for arg in args
        )
        assert "partner_id" in selected and "listing_id" in selected


class TestSwitchErrorMapping:
    def test_missing_lead_maps_to_404(self):
        err = BaitnaService._translate_switch_error(
            _PgError(C.SQLSTATE_SWITCH_LEAD_NOT_FOUND)
        )
        assert err.status_code == 404
        assert err.code == C.CODE_LEAD_NOT_FOUND

    def test_closed_lead_maps_to_409(self):
        err = BaitnaService._translate_switch_error(
            _PgError(C.SQLSTATE_SWITCH_LEAD_CLOSED)
        )
        assert err.status_code == 409
        assert err.code == C.CODE_ALREADY_CLOSED

    def test_foreign_or_inactive_listing_maps_to_404(self):
        err = BaitnaService._translate_switch_error(
            _PgError(C.SQLSTATE_SWITCH_LISTING_INVALID)
        )
        assert err.status_code == 404
        assert err.code == C.CODE_LISTING_NOT_FOUND

    def test_same_listing_maps_to_409(self):
        err = BaitnaService._translate_switch_error(
            _PgError(C.SQLSTATE_SWITCH_SAME_LISTING)
        )
        assert err.status_code == 409
        assert err.code == C.CODE_SAME_LISTING

    def test_quota_maps_to_409_and_carries_the_eligible_date(self):
        err = BaitnaService._translate_switch_error(
            _PgError(
                C.SQLSTATE_SWITCH_LIMIT,
                message="You have already changed your unit twice with this "
                        "partner. You can change it again after 2026-10-14.",
                details="2026-10-14",
            )
        )
        assert err.status_code == 409
        assert err.code == C.CODE_SWITCH_LIMIT_REACHED
        assert err.data == {"eligible_from": "2026-10-14"}

    def test_the_three_conflicts_are_distinguishable(self):
        """All 409s, so the status alone cannot tell the app which message to
        show or whether a retry is worth offering."""
        codes = {
            BaitnaService._translate_switch_error(_PgError(state)).code
            for state in (
                C.SQLSTATE_SWITCH_LEAD_CLOSED,
                C.SQLSTATE_SWITCH_SAME_LISTING,
                C.SQLSTATE_SWITCH_LIMIT,
            )
        }
        assert len(codes) == 3

    def test_unknown_error_maps_to_500(self):
        err = BaitnaService._translate_switch_error(_PgError("42883"))
        assert err.status_code == 500
        assert err.code == C.CODE_INTERNAL

    def test_sqlstate_recovered_from_the_string_form(self):
        """supabase-py does not always expose .code, so every Baitna SQLSTATE has
        to survive the string scan or it degrades to a 500."""
        from app.modules.baitna.service import _sqlstate_of

        for state in C.BAITNA_SQLSTATES:
            assert _sqlstate_of(Exception('{"code":"' + state + '"}')) == state


class TestSwitchListing:
    LEAD = "11111111-1111-1111-1111-111111111111"
    LISTING = "22222222-2222-2222-2222-222222222222"

    class _Rpc:
        def __init__(self, payload=None, raises=None):
            self.payload = payload
            self.raises = raises
            self.called_with = None

        def rpc(self, name, params):
            self.called_with = (name, params)
            outer = self

            class _Exec:
                def execute(self):
                    if outer.raises:
                        raise outer.raises
                    return type("Res", (), {"data": outer.payload})()

            return _Exec()

    def _wire(self, monkeypatch, fake):
        monkeypatch.setattr(
            "app.modules.baitna.service.get_supabase_client", lambda: fake
        )

    def test_calls_the_function_with_the_three_ids(self, service, monkeypatch):
        fake = self._Rpc({"lead_id": self.LEAD, "unit_type": "studio",
                          "switches_remaining": 1})
        self._wire(monkeypatch, fake)

        service.switch_listing("student-1", self.LEAD, self.LISTING)

        name, params = fake.called_with
        assert name == "baitna_switch_listing"
        assert params == {
            "p_student_id": "student-1",
            "p_lead_id": self.LEAD,
            "p_listing_id": self.LISTING,
        }

    def test_the_partner_is_never_a_parameter(self, service, monkeypatch):
        """It is read off the lead inside the function, which is what stops this
        endpoint moving a student to a partner they never consented to."""
        fake = self._Rpc({"unit_type": "studio", "switches_remaining": 0})
        self._wire(monkeypatch, fake)
        service.switch_listing("student-1", self.LEAD, self.LISTING)
        assert "p_partner_id" not in fake.called_with[1]

    def test_message_pluralises_the_remaining_count(self, service, monkeypatch):
        self._wire(monkeypatch, self._Rpc({"unit_type": "studio",
                                           "switches_remaining": 1}))
        one = service.switch_listing("student-1", self.LEAD, self.LISTING)
        assert "1 more time " in one["message"]

        self._wire(monkeypatch, self._Rpc({"unit_type": "studio",
                                           "switches_remaining": 0}))
        none = service.switch_listing("student-1", self.LEAD, self.LISTING)
        assert "0 more times " in none["message"]

    def test_a_row_wrapped_in_a_list_is_unwrapped(self, service, monkeypatch):
        self._wire(monkeypatch, self._Rpc([{"unit_type": "studio",
                                            "switches_remaining": 1}]))
        result = service.switch_listing("student-1", self.LEAD, self.LISTING)
        assert result["unit_type"] == "studio"

    def test_an_empty_result_is_a_500_not_a_silent_success(self, service, monkeypatch):
        self._wire(monkeypatch, self._Rpc(None))
        with pytest.raises(BaitnaError) as exc:
            service.switch_listing("student-1", self.LEAD, self.LISTING)
        assert exc.value.status_code == 500

    def test_malformed_lead_id_is_a_404_not_a_500(self, service, monkeypatch):
        """A bad uuid would otherwise reach Postgres as a failed cast."""
        self._wire(monkeypatch, self._Rpc({}))
        for bad in ["not-a-uuid", "", "123"]:
            with pytest.raises(BaitnaError) as exc:
                service.switch_listing("student-1", bad, self.LISTING)
            assert exc.value.status_code == 404
            assert exc.value.code == C.CODE_LEAD_NOT_FOUND

    def test_malformed_listing_id_is_a_404_too(self, service, monkeypatch):
        self._wire(monkeypatch, self._Rpc({}))
        with pytest.raises(BaitnaError) as exc:
            service.switch_listing("student-1", self.LEAD, "not-a-uuid")
        assert exc.value.status_code == 404
        assert exc.value.code == C.CODE_LISTING_NOT_FOUND

    def test_database_errors_are_translated(self, service, monkeypatch):
        self._wire(
            monkeypatch,
            self._Rpc(raises=_PgError(C.SQLSTATE_SWITCH_LIMIT, details="2026-10-14")),
        )
        with pytest.raises(BaitnaError) as exc:
            service.switch_listing("student-1", self.LEAD, self.LISTING)
        assert exc.value.code == C.CODE_SWITCH_LIMIT_REACHED

    def test_the_request_body_takes_only_a_listing(self):
        """No partner_id field, so the body cannot redirect the inquiry
        elsewhere."""
        assert set(ListingSwitchRequest.model_fields) == {"listing_id"}

    def test_a_malformed_listing_id_is_rejected_by_the_schema(self):
        with pytest.raises(ValidationError):
            ListingSwitchRequest(listing_id="not-a-uuid")



class TestAcknowledgedCannotSwitch:
    """
    Once the partner has replied, the unit on the inquiry is settled. The lead is
    still live — the student can withdraw it — but it can no longer be moved.
    """

    LEAD = "11111111-1111-1111-1111-111111111111"
    LISTING = "22222222-2222-2222-2222-222222222222"

    def test_acknowledged_maps_to_its_own_409(self):
        err = BaitnaService._translate_switch_error(
            _PgError(C.SQLSTATE_SWITCH_ACKNOWLEDGED)
        )
        assert err.status_code == 409
        assert err.code == C.CODE_ALREADY_ACKNOWLEDGED
        assert "already responded" in err.message

    def test_it_is_not_reported_as_a_closed_inquiry(self):
        """ALREADY_CLOSED would tell the student their inquiry is over, when it
        is live and they can still withdraw it."""
        acknowledged = BaitnaService._translate_switch_error(
            _PgError(C.SQLSTATE_SWITCH_ACKNOWLEDGED)
        )
        closed = BaitnaService._translate_switch_error(
            _PgError(C.SQLSTATE_SWITCH_LEAD_CLOSED)
        )
        assert acknowledged.code != closed.code
        assert "closed" not in acknowledged.message.lower()

    def test_the_lead_row_hides_the_button(self, service, monkeypatch):
        row = build_lead_row(
            {
                "id": "lead-1",
                "lead_reference": "BAITNA-NES-260819-0042",
                "status": "acknowledged",
                "listing_id": "listing-1",
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "acknowledged_at": datetime.now(timezone.utc).isoformat(),
                "baitna_partners": {"name": "Nescapmus"},
                "baitna_listings": {"unit_type": "studio"},
            },
            switches_used=0,
        )
        assert row["can_switch_listing"] is False
        # Still live: the other two actions are unchanged by this rule.
        assert row["can_withdraw"] is True

    def test_an_unspent_allowance_does_not_reopen_it(self, service):
        """The status check has to come first — plenty of switches left is not a
        reason to move an acknowledged lead."""
        assert compute_switches_remaining(0, limit=2) == 2
        assert compute_can_switch_listing("acknowledged", 0, limit=2) is False

    def test_the_endpoint_surfaces_the_database_refusal(self, service, monkeypatch):
        """The service flag is only advice; the function is what actually
        enforces it, so a stale client still gets the right answer."""

        class _Rpc:
            def rpc(self, name, params):
                class _Exec:
                    def execute(self):
                        raise _PgError(
                            C.SQLSTATE_SWITCH_ACKNOWLEDGED,
                            message="This partner has already responded to your "
                                    "inquiry, so its unit can no longer be changed.",
                        )

                return _Exec()

        monkeypatch.setattr(
            "app.modules.baitna.service.get_supabase_client", lambda: _Rpc()
        )
        with pytest.raises(BaitnaError) as exc:
            service.switch_listing("student-1", self.LEAD, self.LISTING)
        assert exc.value.status_code == 409
        assert exc.value.code == C.CODE_ALREADY_ACKNOWLEDGED

    def test_rerouting_and_switching_agree_about_acknowledged(self):
        """Both refuse it for the same reason: the partner did respond, so there
        is neither silence to route away from nor an unworked unit to move."""
        assert "acknowledged" not in C.FALLBACK_ELIGIBLE_STATUSES
        assert "acknowledged" not in C.SWITCH_ELIGIBLE_STATUSES

# ================================
# THE SWITCH MIGRATION AND THE CODE AGREE
# ================================

class TestSwitchSqlAgrees:
    """
    baitna_switch_listing is the authority on the quota and on which leads may
    move. The service only decides what the app is told it has left, so drift
    shows a button the database then refuses.
    """

    MIGRATION = (
        Path(__file__).resolve().parents[2]
        / "migrations" / "versions" / "20260914_add_baitna_switch_and_distance.sql"
    )

    def sql(self):
        return self.MIGRATION.read_text(encoding="utf-8")

    def test_switch_quota_matches_the_function(self):
        from app.core.config import Settings

        limit = re.search(
            r"c_limit\s+constant\s+integer\s*:=\s*(\d+)", self.sql()
        )
        assert limit, "the declared allowance was not found in baitna_switch_listing"
        assert int(limit.group(1)) == Settings().BAITNA_LISTING_SWITCH_LIMIT

    def test_the_allowance_is_written_down_only_once(self):
        """The function both enforces the allowance and reports what is left of
        it. Written as two literals, raising the limit in one place and not the
        other would tell the student they have a switch the function refuses —
        and this suite would not notice."""
        sql = self.sql()
        assert "IF v_used >= c_limit THEN" in sql
        assert "c_limit - (v_used + 1)" in sql
        assert not re.search(r"IF v_used >= \d", sql)

    def test_switch_window_matches_the_function(self):
        from app.core.config import Settings

        intervals = set(re.findall(r"interval '(\d+) days'", self.sql()))
        assert intervals, "no rolling window found"
        assert intervals == {str(Settings().BAITNA_LISTING_SWITCH_WINDOW_DAYS)}

    def test_the_switchable_statuses_match_the_function(self):
        """Narrower SQL refuses a lead the service shows a button on; wider SQL
        lets a settled or closed inquiry be moved."""
        guard = re.search(r"v_lead\.status NOT IN \(([^)]*)\)", self.sql())
        assert guard, "switchable-status guard not found in baitna_switch_listing"
        assert set(re.findall(r"'([a-z_]+)'", guard.group(1))) == set(
            C.SWITCH_ELIGIBLE_STATUSES
        )

    def test_the_function_turns_acknowledged_leads_away(self):
        """And with its own SQLSTATE, so the student is told the partner replied
        rather than that their inquiry is closed."""
        sql = self.sql()
        assert re.search(
            r"IF v_lead\.status = 'acknowledged' THEN.*?ERRCODE = 'BT010'", sql, re.S
        )
        assert "acknowledged" not in re.search(
            r"v_lead\.status NOT IN \(([^)]*)\)", sql
        ).group(1)

    def test_the_switchable_set_is_a_subset_of_the_open_set(self):
        """A status the function accepts but the unique index treats as closed
        would let a lead be moved after it stopped blocking new inquiries."""
        assert C.SWITCH_ELIGIBLE_STATUSES <= C.OPEN_STATUSES

    def test_the_function_is_not_callable_with_the_anon_key(self):
        """The anon key ships inside the mobile app; anyone holding it must not
        be able to move someone else's inquiry."""
        sql = self.sql()
        assert re.search(
            r"REVOKE ALL ON FUNCTION baitna_switch_listing[^;]*anon", sql, re.S
        )
        assert re.search(
            r"GRANT EXECUTE ON FUNCTION baitna_switch_listing[^;]*service_role",
            sql, re.S,
        )

    def test_the_switch_log_has_row_level_security(self):
        assert (
            "ALTER TABLE baitna_lead_listing_switches ENABLE ROW LEVEL SECURITY"
            in self.sql()
        )

    def test_the_partner_comes_from_the_lead_not_the_caller(self):
        """The one line keeping a switch inside the partner the student already
        consented to."""
        assert "AND partner_id = v_lead.partner_id" in self.sql()

    def test_every_sqlstate_the_function_raises_is_mapped(self):
        raised = set(re.findall(r"ERRCODE = '(BT\d+)'", self.sql()))
        assert raised, "no SQLSTATEs found in the switch function"
        assert raised <= set(C.BAITNA_SQLSTATES)
        for state in raised:
            err = BaitnaService._translate_switch_error(_PgError(state))
            assert err.code != C.CODE_INTERNAL, state + " falls through to a 500"

    def test_coordinates_are_added_to_both_sides_of_the_calculation(self):
        sql = self.sql()
        for table in ("baitna_partners", "university_domains"):
            assert re.search(
                r"ALTER TABLE " + table + r"\s+ADD COLUMN IF NOT EXISTS latitude", sql
            ), table

    def test_seeded_coordinates_do_not_overwrite_corrected_ones(self):
        """A coordinate fixed by hand must survive a re-run of the migration."""
        sql = self.sql()
        assert "AND u.latitude IS NULL" in sql
        assert "AND u.longitude IS NULL" in sql
