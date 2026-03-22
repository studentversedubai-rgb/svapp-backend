"""
SV Orbit Router — Phase 5 Hardened

Security:
  - LLM API key loaded from env OPENROUTER_API_KEY (via Settings). Never exposed in responses.
  - Message sanitized (max 500 chars, non-empty) at schema level.

Rate Limiting:
  - 10 requests/min per user (velocity) — enforced BEFORE LLM call.
  - 150 requests/24h per user (daily) — enforced BEFORE LLM call.

Reliability:
  - Circuit breaker: 5 consecutive LLM failures → 60s service pause.
  - 10-second timeout on every LLM call.
  - Graceful degradation on timeout.

Analytics:
  - Every successful /orbit/chat call logs an orbit_chat event.

Endpoints:
  - GET  /orbit/health — liveness check
  - POST /orbit/chat   — main AI chat endpoint
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_user
from app.core.config import Settings
from app.core.ratelimit import RateLimiter
from app.core.database import get_supabase_client
from app.modules.orbit.schemas import (
    OrbitChatRequest,
    OrbitChatResponse
)
from app.modules.orbit.service import OrbitService

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize settings
settings = Settings()

# ── Circuit Breaker ────────────────────────────────────────────────────────────
# Simple in-process circuit breaker. Resets on process restart (acceptable for
# this scale — a Redis-backed version would be used for multi-replica deploys).
_cb_failures   = 0                  # consecutive LLM failures
_cb_open_until = 0.0                # epoch seconds when circuit re-closes
CB_FAILURE_THRESHOLD = 5            # open after this many consecutive failures
CB_COOLDOWN_SECONDS  = 60          # how long the circuit stays open

# Feature flag check
if not settings.FEATURE_SV_ORBIT_ENABLED:
    logger.warning("SV Orbit feature is disabled")


# ── Health ─────────────────────────────────────────────────────────────────────
@router.get("/health")
async def orbit_health():
    """Liveness check — returns 200 if Orbit is accepting requests."""
    global _cb_open_until
    if not settings.FEATURE_SV_ORBIT_ENABLED:
        raise HTTPException(status_code=503, detail="Orbit is currently disabled")
    if time.time() < _cb_open_until:
        remaining = int(_cb_open_until - time.time())
        raise HTTPException(
            status_code=503,
            detail=f"Orbit temporarily unavailable. Retry in {remaining}s."
        )
    return {"status": "ok", "service": "orbit"}


# ── Analytics helper ───────────────────────────────────────────────────────────
def _log_orbit_event(user_id: str, session_id: str, mode: str, metadata: dict):
    """Fire-and-forget analytics event — failures are non-fatal."""
    try:
        client = get_supabase_client()
        if not client:
            return
        client.table("analytics_events").insert({
            "user_id": user_id,
            "event_type": "orbit_chat",
            "event_data": {
                "user_id": user_id,
                "session_id": session_id,
                "mode": mode,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **metadata,
            },
        }).execute()
    except Exception as exc:
        logger.warning(f"Failed to log orbit_chat event: {exc}")



# ── Chat ───────────────────────────────────────────────────────────────────────
@router.post("/chat", response_model=OrbitChatResponse)
async def orbit_chat(
    request: OrbitChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Chat with Orbit AI assistant.

    Security:
      Rate limits checked BEFORE the LLM call.
      API key never included in any response.

    Flow:
      1. Feature-flag guard
      2. Circuit-breaker guard
      3. Rate-limit check (velocity + daily)
      4. LLM call with 10-second timeout
      5. Analytics event
      6. Return structured response
    """
    global _cb_failures, _cb_open_until

    # 1. Feature flag
    if not settings.FEATURE_SV_ORBIT_ENABLED:
        raise HTTPException(status_code=503, detail="Orbit is currently unavailable")

    # 2. Circuit breaker
    if time.time() < _cb_open_until:
        remaining = int(_cb_open_until - time.time())
        raise HTTPException(
            status_code=503,
            detail=f"Orbit is temporarily unavailable. Please try again in {remaining} seconds."
        )

    # 3. Rate limits — enforced BEFORE the LLM call
    RateLimiter.check_limits(
        user_id=current_user["id"],
        daily_limit=settings.DAILY_CHAT_LIMIT
    )

    # Validate + normalize mode (default to chat if unrecognised)
    from app.modules.orbit.schemas import OrbitMode
    try:
        mode = OrbitMode(request.mode) if request.mode else OrbitMode.CHAT
    except ValueError:
        mode = OrbitMode.CHAT

    service = OrbitService(settings)

    try:
        # 4. LLM call — hard 10-second timeout
        response = await asyncio.wait_for(
            service.chat(
                user_id=current_user["id"],
                message=request.message,
                session_id=request.session_id,
                latitude=request.latitude,
                longitude=request.longitude,
                mode=mode,
            ),
            timeout=10.0
        )

        # Reset circuit breaker on success
        _cb_failures = 0

        # 5. Analytics (non-blocking, best-effort)
        _log_orbit_event(
            user_id=current_user["id"],
            session_id=response.session_id or "",
            mode=mode.value,
            metadata={
                "offers_shown": len(response.plans),
                "intent": (response.metadata or {}).get("intent", ""),
            }
        )

        return response

    except asyncio.TimeoutError:
        _cb_failures += 1
        if _cb_failures >= CB_FAILURE_THRESHOLD:
            _cb_open_until = time.time() + CB_COOLDOWN_SECONDS
            logger.error(f"Orbit circuit breaker OPEN after {_cb_failures} failures")
        raise HTTPException(
            status_code=503,
            detail="Orbit took too long to respond. Please try again in a moment."
        )

    except HTTPException:
        raise

    except Exception as e:
        _cb_failures += 1
        if _cb_failures >= CB_FAILURE_THRESHOLD:
            _cb_open_until = time.time() + CB_COOLDOWN_SECONDS
            logger.error(f"Orbit circuit breaker OPEN after {_cb_failures} failures")
        logger.error(f"Error in orbit chat: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Orbit Error: {str(e)}"
        )
