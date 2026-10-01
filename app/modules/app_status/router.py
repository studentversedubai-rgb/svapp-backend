"""
App Status Router

Public read-only endpoint for the mobile app to fetch the current lockout /
alert configuration. Dashboard writes directly to Supabase (service role),
so no write endpoints are exposed here.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.admin_auth import require_internal_admin
from app.modules.app_status import service
from app.modules.app_status.schemas import AppStatus, BaitnaVisibilityUpdate

router = APIRouter()


@router.get(
    "",
    response_model=AppStatus,
    summary="Get current app status",
    description=(
        "Returns the current app-wide status (normal | maintenance | emergency | "
        "force_update | custom) plus any craft fields for the custom alert screen. "
        "Public endpoint — no auth required."
    ),
)
async def read_app_status() -> AppStatus:
    return await service.get_app_status()


@router.get("/visibility")
async def read_baitna_visibility(_actor: str = Depends(require_internal_admin)) -> dict[str, bool]:
    return {"baitna_visible": service.get_baitna_visibility()}


@router.put("/visibility")
async def update_baitna_visibility(
    payload: BaitnaVisibilityUpdate,
    _actor: str = Depends(require_internal_admin),
) -> dict[str, bool]:
    if not service.set_baitna_visibility(payload.visible):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Unable to save Baitna visibility.")
    return {"baitna_visible": payload.visible}
