"""
Internal Admin API authentication helpers.
"""

import hashlib
import hmac
import time

from fastapi import Header, HTTPException, status

from app.core.config import Settings


async def require_internal_admin(
    x_admin_token: str = Header(default="", alias="X-Admin-Token"),
    x_admin_actor: str = Header(default="sv-dashboard", alias="X-Admin-Actor"),
    x_admin_timestamp: str = Header(default="", alias="X-Admin-Timestamp"),
    x_admin_signature: str = Header(default="", alias="X-Admin-Signature"),
) -> str:
    settings = Settings()

    if settings.ADMIN_API_TOKEN:
        authenticated = hmac.compare_digest(x_admin_token, settings.ADMIN_API_TOKEN)
    else:
        try:
            timestamp = int(x_admin_timestamp)
        except ValueError:
            timestamp = 0
        expected = hmac.new(
            settings.SUPABASE_SERVICE_KEY.encode(),
            x_admin_timestamp.encode(),
            hashlib.sha256,
        ).hexdigest()
        authenticated = abs(int(time.time()) - timestamp) <= 60 and hmac.compare_digest(
            x_admin_signature,
            expected,
        )

    if not authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials.",
        )

    return x_admin_actor or "sv-dashboard"
