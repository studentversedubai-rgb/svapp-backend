"""
Internal Admin API authentication helpers.
"""

from fastapi import Header, HTTPException, status

from app.core.config import Settings


async def require_internal_admin(
    x_admin_token: str = Header(default="", alias="X-Admin-Token"),
    x_admin_actor: str = Header(default="sv-dashboard", alias="X-Admin-Actor"),
) -> str:
    settings = Settings()

    if not settings.ADMIN_API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ADMIN_API_TOKEN is not configured.",
        )

    if x_admin_token != settings.ADMIN_API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials.",
        )

    return x_admin_actor or "sv-dashboard"
