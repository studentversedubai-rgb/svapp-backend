# Baitna API: Frontend Reference

Student housing inquiries. All routes are mounted under `/baitna`.

---

## Response envelope

Every Baitna route returns this shape, success or failure. Never read the HTTP
status alone; branch on `code`.

```jsonc
// success
{ "ok": true, "data": { ... } }

// failure
{ "ok": false, "error": "Human-readable sentence, safe to show the user.",
  "code": "MACHINE_CODE", "data": { ... } }   // code and data may be absent
```

`error` is written for the student and can be displayed as-is. `code` is what you
branch on: several different failures share HTTP 409.

## Auth

Every route except `GET /baitna/status` needs a student JWT:

```
Authorization: Bearer <access_token>
```

Send `X-Device-ID` only if the rest of your app already does. A mismatch against
the stored device returns **403** across the whole API, not just Baitna.

## Feature flag

While Baitna is switched off server-side, every route **404s** as though it were
never deployed. `GET /baitna/status` is the exception: call it first and use
`tile_visible` to decide whether to render the Baitna entry point at all.

---

# Endpoints

## `GET /baitna/status`

Public, no auth. Call on launch to decide whether to show the Baitna tile.

```jsonc
{ "active_partner_count": 4, "tile_visible": true }
```

Never errors: on a backend problem it reports `0` / `false` rather than failing,
so a broken call means "hide the tile", not "show an error".

---

## `GET /baitna/partners`

Every active partner with its active listings. This is the tile screen.

```jsonc
{ "partners": [{
  "id": "uuid",
  "name": "Sample Residences",
  "property_name": "Sample Campus",        // nullable
  "logo_url": "https://...",               // nullable
  "price_disclosure_enabled": true,
  "distance_km": 12.4,                     // nullable, see below
  "distance_label": "12.4 km away from Zayed University (ZU)",  // nullable
  "listings": [ /* Listing objects, see below */ ]
}]}
```

**`distance_km` / `distance_label` are frequently null.** Straight-line distance
from the partner to the caller's university, and both are null when the partner
has no coordinates on file or we can't place the student's university. **Render
the tile with no distance row in that case, never fall back to `0`.** Use
`distance_label` directly; it already contains the figure and the university name.

---

## `GET /baitna/listings`

Flat paginated feed across all partners. This is the browse/search screen.

**Query parameters**, all optional:

| Param | Type | Notes |
|---|---|---|
| `unit_type` | enum, repeatable | `?unit_type=studio&unit_type=en_suite` |
| `availability_status` | enum, repeatable | Defaults to `available` + `limited` |
| `partner_id` | uuid | |
| `bedrooms_min`, `bathrooms_min`, `living_rooms_min` | int ≥ 0 | |
| `area_sqft_min`, `area_sqft_max` | float > 0 | min > max → 422 |
| `price_min`, `price_max` | float ≥ 0 | min > max → 422 |
| `has_spots_available` | bool | `true` keeps only listings with room left |
| `sort` | `popularity` \| `price` \| `area_sqft` \| `bedrooms` \| `newest` | default `popularity` |
| `order` | `asc` \| `desc` | default `desc` |
| `page` | int ≥ 1 | default 1 |
| `page_size` | int ≥ 1 | default 20, silently clamped to 50 |

```jsonc
{ "listings": [ /* Listing + partner_id, partner_name, property_name, logo_url */ ],
  "page": 1, "page_size": 20, "total": 137 }
```

Listings from partners who hide prices are **excluded from `price_min`/`price_max`
filters** and always sort last under `sort=price`. That's deliberate: it stops a
hidden price being narrowed down. Don't treat their absence from a price filter as
a bug.

---

## `GET /baitna/leads`

The student's own inquiries, newest first. Drives the "My inquiries" screen.

```jsonc
{ "leads": [{
  "id": "uuid",
  "lead_reference": "BAITNA-AZIZ-260819-0042",
  "partner_name": "Sample Residences",
  "property_name": "Sample Campus",        // nullable
  "listing_id": "uuid",                    // the unit currently on the inquiry
  "unit_type": "studio",                   // nullable
  "unit_type_label": "Studio",             // nullable
  "status": "posted_to_dashboard",
  "status_label": "Awaiting Response",     // display this, not `status`
  "submitted_at": "2026-08-19T10:04:00Z",
  "acknowledged_at": null,
  "can_withdraw": true,
  "can_fallback": false,
  "can_switch_listing": true,
  "switches_remaining": 2
}]}
```

**Draw every action button from the `can_*` flags, never from `status`.** The three
flags do not move together:

- `can_withdraw`: true while the inquiry is live, **including after the partner
  acknowledges it**.
- `can_switch_listing`: true only while the partner has **not** replied yet, and
  only while `switches_remaining > 0`.
- `can_fallback`: true only once the inquiry has sat unanswered for 7 days.

`switches_remaining` is the student's allowance with that partner and stays
accurate even when `can_switch_listing` is false. Gate the whole control on
`can_switch_listing`; don't show "2 switches left" next to a disabled button.

---

## `POST /baitna/leads`

Submit an inquiry. **201** on success.

```jsonc
{
  "partner_id": "uuid",
  "listing_id": "uuid",
  "move_in_date": "2026-10-01",      // not past, max 730 days ahead
  "lease_length_months": 12,          // 1–60
  "budget_band": "3500_5000",
  "current_status": "arriving_soon",
  "consent": {
    "consent_version": "baitna_v1",
    "consent_text_snapshot": "the exact consent copy you showed the student",
    "data_transfers_outside_uae": false,
    "dpo_contact": "privacy@example.com"   // optional
  }
}
```

`consent_text_snapshot` must be **the literal text rendered on screen**. It's
stored verbatim as the legal record of what was agreed, so don't send a summary,
a key, or a translation the student didn't see.

```jsonc
{ "id": "uuid", "lead_reference": "BAITNA-AZIZ-260819-0042",
  "status": "posted_to_dashboard", "partner_name": "...",
  "submitted_at": "...", "message": "Your inquiry has been submitted..." }
```

| Code | HTTP | Meaning |
|---|---|---|
| `OPEN_INQUIRY_EXISTS` | 409 | Already an open inquiry with this partner |
| `COOLDOWN_ACTIVE` | 409 | One closed <30 days ago. `data.eligible_from` = ISO date |
| `PARTNER_NOT_FOUND` | 404 | Partner or listing missing or inactive |

---

## `POST /baitna/leads/{lead_id}/listing/switch`

Move an open inquiry onto a different unit **from the same partner**. Show this
next to Withdraw when `can_switch_listing` is true.

```jsonc
{ "listing_id": "uuid" }
```

There is no `partner_id` field: it's read from the inquiry, so this can only ever
move the student between units of the partner they already consented to. Source
the target from `GET /baitna/partners` or `GET /baitna/listings?partner_id=...`.

The inquiry keeps its `lead_reference`, its consent record and its submitted date.
Only the unit changes.

```jsonc
{ "lead_id": "uuid", "lead_reference": "BAITNA-AZIZ-260819-0042",
  "partner_id": "uuid", "partner_name": "...", "property_name": "...",
  "listing_id": "uuid",          "unit_type": "one_bed",
  "previous_listing_id": "uuid", "previous_unit_type": "studio",
  "switches_used": 1, "switches_remaining": 1,
  "switched_at": "...", "message": "Your inquiry has been moved to the 1-Bedroom Apartment..." }
```

**Limit: 2 per partner per rolling 30 days.**

| Code | HTTP | Meaning |
|---|---|---|
| `SWITCH_LIMIT_REACHED` | 409 | Allowance spent. `data.eligible_from` = ISO date |
| `ALREADY_ACKNOWLEDGED` | 409 | Partner replied, the unit is now fixed. **Still withdrawable** |
| `ALREADY_CLOSED` | 409 | Inquiry is closed |
| `SAME_LISTING` | 409 | That unit is already on the inquiry |
| `LISTING_NOT_FOUND` | 404 | Unit inactive, or belongs to another partner |
| `LEAD_NOT_FOUND` | 404 | No such inquiry for this student |

`ALREADY_ACKNOWLEDGED` and `ALREADY_CLOSED` are both 409 but mean different
things: an acknowledged inquiry is still **live**, so keep Withdraw enabled and
don't tell the student their inquiry is over.

---

## `POST /baitna/leads/{lead_id}/consent/withdraw`

Revokes consent and closes the inquiry. Body optional.

```jsonc
{ "reason": "Found somewhere else" }   // optional, max 1000 chars
```

```jsonc
{ "lead_reference": "...", "status": "withdrawn", "withdrawn_at": "...",
  "message": "Your inquiry has been withdrawn and your consent has been revoked." }
```

**Terminal and irreversible.** It also starts a 30-day block on new inquiries to
that same partner, so confirm before calling. `ALREADY_CLOSED` (409) if already
closed.

---

## `POST /baitna/leads/{lead_id}/fallback/route`

Reroute a stalled inquiry to a different partner. Offer when `can_fallback` is
true. Body optional; omit it to keep the original move-in date. **201** on success.

```jsonc
{ "move_in_date": "2026-11-01" }   // optional
```

```jsonc
{ "new_lead_id": "uuid", "new_lead_reference": "...", "new_partner_name": "...",
  "original_lead_reference": "...", "original_lead_status": "routed",
  "move_in_date": "2026-11-01", "message": "..." }
```

| Code | HTTP | Meaning |
|---|---|---|
| `NOT_FALLBACK_ELIGIBLE` | 409 | Not stalled long enough, or not open |
| `NO_FALLBACK_MATCH` | 404 | Nothing available. `data.dubizzle_url`, `data.bayut_url` |
| `MOVE_IN_DATE_REQUIRED` | 409 | Original date has passed, prompt for a new one and retry |

`MOVE_IN_DATE_REQUIRED` is a prompt, not a dead end: ask for a date, resend.

---

## `POST /baitna/leads/{lead_id}/fallback/resend`

Re-sends the student's confirmation email. Changes nothing. No body.

```jsonc
{ "message": "Confirmation email resent to your registered email." }
```

`ALREADY_CLOSED` (409) on a closed inquiry, `EMAIL_FAILED` (502) if the send fails.
On 502 it's safe to offer a retry.

---

# Enums

```
unit_type            en_suite | studio | shared_twin | one_bed | two_bed
availability_status  available | limited | waitlist | unavailable
budget_band          under_2000 | 2000_3500 | 3500_5000 | 5000_8000 | above_8000
current_status       in_university_housing | in_private_housing | arriving_soon | looking_to_move
status               submitted | posted_to_dashboard | acknowledged | aging |
                     converted | routed | withdrawn | closed_no_match | expired_stale
```

Every response carries a matching `*_label` field. **Display the label, not the
raw value**: `aging` is shown to students as "Awaiting Response".

## Listing object

```jsonc
{ "id": "uuid", "unit_type": "studio", "unit_type_label": "Studio",
  "price_amount": 3500,                        // null when the partner hides prices
  "price_currency": "AED",
  "price_display": "AED 3,500 / month",        // or "Confirmed on inquiry"
  "image_urls": ["https://..."],
  "availability_status": "available", "availability_label": "Available",
  "bedrooms": 1, "bathrooms": 1, "living_rooms": 0,   // all nullable
  "area_sqft": 480, "occupancy_max": 2, "occupants_current": 1,
  "spots_available": 1, "lead_count": 7 }
```

Always render `price_display` rather than formatting `price_amount` yourself: it
already reads `"Confirmed on inquiry"` when the partner hides prices, and
`price_amount` is `null` in that case.

`lead_count` is a popularity signal, not a count of inquiries.

---

# Rate limits

Per student, fixed window, **429** when exceeded.

| Endpoint | Limit |
|---|---|
| `POST /leads` and `POST /fallback/route` (shared budget) | 5 / hour |
| `POST /listing/switch` | 10 / hour |
| `POST /fallback/resend` | 3 / hour |

The switch limit counts failed attempts too, so don't retry automatically on a
4xx: those are permanent answers.

---

# Error codes at a glance

| Code | HTTP |
|---|---|
| `OPEN_INQUIRY_EXISTS`, `COOLDOWN_ACTIVE` | 409 |
| `ALREADY_CLOSED`, `ALREADY_ACKNOWLEDGED`, `SAME_LISTING`, `SWITCH_LIMIT_REACHED` | 409 |
| `NOT_FALLBACK_ELIGIBLE`, `MOVE_IN_DATE_REQUIRED` | 409 |
| `PARTNER_NOT_FOUND`, `LISTING_NOT_FOUND`, `LEAD_NOT_FOUND`, `NO_FALLBACK_MATCH` | 404 |
| `STUDENT_NOT_FOUND` | 401, sign the user out and re-authenticate |
| `EMAIL_FAILED` | 502, retryable |
| `INTERNAL_ERROR` | 500, retryable |

Anything with `eligible_from` in `data` is a temporary block, show the date.
Everything else 4xx is permanent until the student does something different.
