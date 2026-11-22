"""
Security Module

Handles JWT verification using python-jose (custom JWT, no Supabase Auth).
"""

import logging
from typing import Optional, Dict

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from app.core.database import fetch_one, execute
from app.core.config import get_settings
from app.core.activity import touch_last_active


logger = logging.getLogger(__name__)

# Security scheme for JWT bearer tokens
security = HTTPBearer()


def _resolve_token_user(token: str) -> Dict[str, str]:
    """
    Decode a JWT and return {"sub": user_id, "email": email}.

    Raises HTTPException 401 on any JWTError or missing sub.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {"sub": str(user_id), "email": payload.get("email")}


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict:
    """
    Dependency to get current authenticated user from JWT.

    Validates JWT with python-jose and fetches user from public.users.

    Also enforces device binding security if X-Device-ID header is present.

    Args:
        request: Incoming HTTP request (used for device-id header + state).
        credentials: HTTP Authorization header with Bearer token.

    Returns:
        User dict with id, email, name, etc.

    Raises:
        HTTPException: 401 if authentication fails.
        HTTPException: 403 if device mismatch or account not approved.
        HTTPException: 404 if user profile not found.
        HTTPException: 500 on internal errors.
    """
    token = credentials.credentials

    try:
        payload = _resolve_token_user(token)
        user_id = payload["sub"]

        # Fetch user details from public.users
        try:
            user = await fetch_one("SELECT * FROM users WHERE id = %s", (user_id,))

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User profile not found",
                )

            verification_status = user.get("verification_status")
            if verification_status and verification_status != "approved":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": (
                            "ACCOUNT_PENDING_REVIEW"
                            if verification_status == "pending_review"
                            else "ACCOUNT_REJECTED"
                        ),
                        "message": "Your account is not approved for app access yet.",
                        "verification_status": verification_status,
                        "review_reason": user.get("verification_rejection_reason"),
                    },
                )

            # --- Device Security Check ---
            device_id_header = request.headers.get("X-Device-ID")
            stored_device_id = user.get("device_id")

            if device_id_header:
                if stored_device_id:
                    # Case 1: User has a stored device ID — check for mismatch.
                    if stored_device_id != device_id_header:
                        logger.warning(
                            f"Device mismatch for user {user_id}. "
                            f"Stored: {stored_device_id}, Header: {device_id_header}"
                        )
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Device mismatch. Single device login enforced.",
                        )
                else:
                    # Case 2: User has NO stored device ID — bind this device.
                    logger.info(f"Binding first device {device_id_header} to user {user_id}")
                    try:
                        await execute(
                            "UPDATE users SET device_id = %s WHERE id = %s",
                            (device_id_header, user_id),
                        )
                        user["device_id"] = device_id_header  # Update local object
                    except Exception as e:
                        logger.error(f"Failed to bind device: {e}")
                        # Non-critical — allow access, retry on next request.

            # Heartbeat: bump last_active_at (throttled to 30 s).
            app_version = getattr(getattr(request, "state", None), "app_version", None)
            touch_last_active(
                user_id,
                app_version=app_version,
                last_active_at_existing=user.get("last_active_at"),
            )

            return user

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to fetch user profile: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve user data",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_optional_user(request: Request) -> Optional[Dict]:
    """
    Optional auth dependency. Returns the user dict when a valid Bearer token
    is supplied, otherwise None. Never raises for missing/invalid tokens.

    Used for read-only endpoints that should be accessible to guests but may
    still want to personalise responses when a user IS signed in.
    """
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None

    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None

    try:
        try:
            payload = _resolve_token_user(token)
            user_id = payload["sub"]
        except HTTPException:
            return None

        user = await fetch_one("SELECT * FROM users WHERE id = %s", (user_id,))
        if not user:
            return None

        verification_status = user.get("verification_status")
        if verification_status and verification_status != "approved":
            return None

        return user
    except Exception as e:
        logger.warning(f"get_optional_user: token validation failed, treating as guest: {e}")
        return None


async def get_current_user_no_device_check(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict:
    """
    Lightweight auth dependency that validates the JWT only (no device check).
    Used for /register where the device_id is being SET for the first time.
    """
    token = credentials.credentials

    try:
        payload = _resolve_token_user(token)
        user_id = payload["sub"]

        user = await fetch_one("SELECT * FROM users WHERE id = %s", (user_id,))

        if not user:
            # User exists in auth but not yet in public.users — return basic info.
            return {"id": str(user_id), "email": payload.get("email")}

        return user

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
