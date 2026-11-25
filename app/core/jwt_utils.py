"""JWT token creation and validation utilities."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

from jose import JWTError, jwt

from app.core.config import get_settings


def create_access_token(user_id: str, email: str, extra_claims: Optional[Dict[str, Any]] = None) -> str:
    """Create a signed JWT access token with 30-day expiry."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": now + timedelta(days=30),
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT. Raises JWTError on failure."""
    settings = get_settings()
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
