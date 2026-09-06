"""Feature-flag gate."""

from fastapi import HTTPException, status

from app.core.config import get_settings


async def require_baitna_enabled() -> None:
    """
    404 while the feature is off, so it looks like a route that was never deployed.

    Changing the flag needs a server restart, not just a reload: settings are
    cached and .env is not watched. GET /baitna/status skips this gate — it answers
    tile_visible: false instead.
    """
    if not get_settings().FEATURE_BAITNA_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
