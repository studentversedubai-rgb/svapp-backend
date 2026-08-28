"""Token resolution for physical StudentVerse counter cards.

This router intentionally does not create a redemption. That happens only after
the student enters their bill in the next step.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.database import get_supabase_client
from app.core.security import get_optional_user

router = APIRouter()


class ResolveVenueRequest(BaseModel):
    token: str


@router.post("/resolve-venue")
async def resolve_venue(
    request: ResolveVenueRequest,
    current_user: Optional[dict] = Depends(get_optional_user),
):
    """Resolve a printed counter-card QR payload to its active dine-in offer."""
    # Counter QR tokens must not be readable through a public RLS policy.
    # This server-side route uses the service-role client after the request has
    # been authenticated/validated by its dependency.
    db = get_supabase_client()
    if not db:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database connection unavailable.")
    venue_result = db.table("dine_in_merchants").select("*").eq("qr_token", request.token).maybe_single().execute()
    venue = venue_result.data
    if not venue or not venue.get("is_active"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This counter card is invalid or inactive.")

    now = datetime.now(timezone.utc)
    valid_from = datetime.fromisoformat(venue["valid_from"].replace("Z", "+00:00"))
    valid_until = datetime.fromisoformat(venue["valid_until"].replace("Z", "+00:00"))
    if now < valid_from or now > valid_until:
        return {
            "merchant": {"id": venue["id"], "name": venue["name"], "logo_url": venue.get("logo_url"), "dine_in": True},
            "branch": {"id": venue["id"], "name": venue["branch_name"], "location": venue["address"]},
            "offer": None,
            "eligibility": "eligible",
        }

    # Guests are not eligible. A future verification service can replace this
    # branch with its authoritative approved-status lookup without changing the client contract.
    eligibility = "eligible" if current_user else "unverified"
    offer = {
        "id": venue["id"], "title": venue["offer_title"],
        "description": venue.get("offer_description") or "Student dine-in discount",
        "offer_type": "percentage", "discount_value": str(venue["discount_percentage"]),
        "redemption_mode": "dine_in", "valid_from": venue["valid_from"], "valid_until": venue["valid_until"],
        "merchant": {"id": venue["id"], "name": venue["name"], "logo_url": venue.get("logo_url"), "address": venue["address"], "dine_in": True},
    }
    return {
        "merchant": offer["merchant"],
        "branch": {"id": venue["id"], "name": venue["branch_name"], "location": venue["address"]},
        "offer": offer,
        "eligibility": eligibility,
    }
