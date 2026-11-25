"""
User Activity Tracking

Helpers for writing rows into `user_activity_events` and bumping the
`last_active_at` heartbeat on `users`. Used by the dashboard's
Realtime Users page.

Every helper here is best-effort: failures are logged but never raised,
so activity tracking can never break the calling endpoint.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.core.database import execute, fetch_one, fetch_all

logger = logging.getLogger(__name__)


HEARTBEAT_THROTTLE_SECONDS = 30


def get_app_version_platform(request) -> tuple[Optional[str], Optional[str]]:
    """Read the app version + platform from request headers (or state)."""
    if request is None:
        return None, None
    state = getattr(request, "state", None)
    app_version = getattr(state, "app_version", None) if state else None
    platform = getattr(state, "platform", None) if state else None
    if not app_version:
        app_version = request.headers.get("X-App-Version") or None
    if not platform:
        raw_platform = request.headers.get("X-Platform")
        platform = (raw_platform or "").lower() or None
        if platform not in ("ios", "android"):
            platform = None
    return app_version, platform


def log_activity_event(
    user_id: str,
    event_type: str,
    *,
    event_data: Optional[Dict[str, Any]] = None,
    app_version: Optional[str] = None,
    platform: Optional[str] = None,
) -> None:
    """Insert a row into user_activity_events. Never raises."""
    if not user_id:
        return
    try:
        execute(
            "INSERT INTO user_activity_events "
            "(user_id, event_type, event_data, app_version, platform) "
            "VALUES (%s, %s, %s::jsonb, %s, %s)",
            (
                user_id,
                event_type,
                json.dumps(event_data or {}),
                app_version,
                platform,
            ),
        )
    except Exception as e:
        logger.error(f"log_activity_event({event_type}) failed for {user_id}: {e}")


def touch_last_active(
    user_id: str,
    *,
    app_version: Optional[str] = None,
    last_active_at_existing: Optional[str] = None,
    force: bool = False,
) -> None:
    """
    Bump users.last_active_at (and last_app_version if provided).

    Throttled: skip the write if the existing last_active_at is within
    HEARTBEAT_THROTTLE_SECONDS, unless force=True. Never raises.
    """
    if not user_id:
        return

    if not force and last_active_at_existing:
        try:
            last = datetime.fromisoformat(last_active_at_existing.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) - last < timedelta(seconds=HEARTBEAT_THROTTLE_SECONDS):
                return
        except Exception:
            pass

    payload: Dict[str, Any] = {"last_active_at": datetime.now(timezone.utc).isoformat()}
    if app_version:
        payload["last_app_version"] = app_version

    try:
        set_clause = ", ".join(f"{k} = %s" for k in payload)
        execute(
            f"UPDATE users SET {set_clause} WHERE id = %s",
            (*payload.values(), user_id),
        )
    except Exception as e:
        logger.error(f"touch_last_active failed for {user_id}: {e}")


def mark_login(
    user_id: str,
    *,
    app_version: Optional[str] = None,
    platform: Optional[str] = None,
) -> None:
    """Update last_login_at + last_active_at + last_app_version and emit a 'login' event."""
    if not user_id:
        return
    now_iso = datetime.now(timezone.utc).isoformat()
    payload: Dict[str, Any] = {
        "last_login_at": now_iso,
        "last_active_at": now_iso,
    }
    if app_version:
        payload["last_app_version"] = app_version
    try:
        set_clause = ", ".join(f"{k} = %s" for k in payload)
        execute(
            f"UPDATE users SET {set_clause} WHERE id = %s",
            (*payload.values(), user_id),
        )
    except Exception as e:
        logger.error(f"mark_login update failed for {user_id}: {e}")

    log_activity_event(
        user_id,
        "login",
        app_version=app_version,
        platform=platform,
    )


def mark_signup_versions(
    user_id: str,
    *,
    app_version: Optional[str],
    platform: Optional[str],
) -> None:
    """Persist signup_app_version + signup_platform when present."""
    if not user_id:
        return
    payload: Dict[str, Any] = {}
    if app_version:
        payload["signup_app_version"] = app_version
        payload["last_app_version"] = app_version
    if platform:
        payload["signup_platform"] = platform
    if not payload:
        return
    try:
        set_clause = ", ".join(f"{k} = %s" for k in payload)
        execute(
            f"UPDATE users SET {set_clause} WHERE id = %s",
            (*payload.values(), user_id),
        )
    except Exception as e:
        logger.error(f"mark_signup_versions failed for {user_id}: {e}")
