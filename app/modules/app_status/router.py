"""
App Status Router

Public read-only endpoint for the mobile app to fetch the current lockout /
alert configuration. Dashboard writes directly to Supabase (service role),
so no write endpoints are exposed here.
"""

from fastapi import APIRouter

from app.modules.app_status import service
from app.modules.app_status.schemas import AppStatus

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
