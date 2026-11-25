from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Any, Dict, Literal, Optional
from app.core.database import fetch_one, execute
from app.core.security import get_current_user
from app.core.redis import redis_manager
from app.core.admin_auth import require_internal_admin
from app.modules.notifications.service import notification_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/push-tokens", tags=["notifications"])
admin_router = APIRouter(prefix="/admin/notifications", tags=["admin-notifications"])


class PushTokenRegister(BaseModel):
    userId: Optional[str] = None
    token: str
    platform: str


class PushTokenUpdate(BaseModel):
    token: str
    platform: str
    isEnabled: Optional[bool] = True


class ApplicationPushTokenRegister(BaseModel):
    registration_token: str
    token: str
    platform: str


class AdminPushRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=500)
    audience: Literal["all", "selected"] = "all"
    user_ids: list[str] = Field(default_factory=list, max_length=500)
    data: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def selected_users_required(self):
        if self.audience == "selected" and not self.user_ids:
            raise ValueError("user_ids is required for a selected audience")
        if self.audience == "all" and self.user_ids:
            raise ValueError("user_ids must be empty for an all-user audience")
        return self


@router.post("")
async def register_push_token(
    payload: PushTokenRegister,
    current_user: dict = Depends(get_current_user),
):
    """
    Register or update a push notification token for a user.
    Frontend sends: { userId, token, platform }
    """
    try:
        current_user_id = str(current_user.get("id"))
        # Verify the requesting user matches the userId in legacy payloads.
        if payload.userId and payload.userId != current_user_id:
            raise HTTPException(status_code=403, detail="Cannot register token for another user")

        existing = fetch_one(
            "SELECT id FROM user_push_tokens WHERE user_id = %s AND push_token = %s",
            (current_user_id, payload.token)
        )

        if existing:
            token_id = existing["id"]
            execute(
                "UPDATE user_push_tokens SET platform = %s WHERE id = %s",
                (payload.platform, token_id)
            )
            logger.info(f"Updated push token for user {current_user_id}")
            return {"success": True, "message": "Push token updated", "tokenId": token_id}
        else:
            new_row = fetch_one(
                "INSERT INTO user_push_tokens (user_id, push_token, platform) VALUES (%s, %s, %s) RETURNING id",
                (current_user_id, payload.token, payload.platform)
            )
            token_id = new_row["id"] if new_row else None
            logger.info(f"Registered new push token for user {current_user_id}")
            return {
                "success": True,
                "message": "Push token registered",
                "tokenId": token_id,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error registering push token: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/application")
async def register_application_push_token(payload: ApplicationPushTokenRegister):
    registration_key = f"sv:app:auth:push_registration:{payload.registration_token}"
    user_id = redis_manager.get(registration_key)
    if not user_id:
        raise HTTPException(status_code=401, detail="Notification registration session expired")

    existing = fetch_one(
        "SELECT id FROM user_push_tokens WHERE push_token = %s LIMIT 1",
        (payload.token,)
    )
    if existing:
        token_id = existing["id"]
        execute(
            "UPDATE user_push_tokens SET user_id = %s, platform = %s WHERE id = %s",
            (str(user_id), payload.platform, token_id)
        )
    else:
        created = fetch_one(
            "INSERT INTO user_push_tokens (user_id, push_token, platform) VALUES (%s, %s, %s) RETURNING id",
            (str(user_id), payload.token, payload.platform)
        )
        token_id = created["id"] if created else None

    redis_manager.delete(registration_key)
    return {"success": True, "message": "Push token registered", "tokenId": token_id}


@router.put("/{user_id}")
async def update_push_token(
    user_id: str,
    payload: PushTokenUpdate,
    current_user: dict = Depends(get_current_user),
):
    """
    Update push token settings for a user.
    """
    try:
        current_user_id = str(current_user.get("id"))
        if user_id != current_user_id:
            raise HTTPException(status_code=403, detail="Cannot update token for another user")

        if payload.isEnabled is False:
            execute("DELETE FROM user_push_tokens WHERE user_id = %s", (user_id,))
        else:
            execute(
                "UPDATE user_push_tokens SET push_token = %s, platform = %s WHERE user_id = %s",
                (payload.token, payload.platform, user_id)
            )

        return {"success": True, "message": "Push token updated"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating push token: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{user_id}")
async def delete_push_token(
    user_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Delete push tokens for a user (disable notifications).
    """
    try:
        current_user_id = str(current_user.get("id"))
        if user_id != current_user_id:
            raise HTTPException(status_code=403, detail="Cannot delete token for another user")

        execute("DELETE FROM user_push_tokens WHERE user_id = %s", (user_id,))
        return {"success": True, "message": "Push token removed"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting push token: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@admin_router.post("/send")
async def send_admin_push(
    payload: AdminPushRequest,
    actor: str = Depends(require_internal_admin),
):
    try:
        result = await notification_service.send_campaign(
            title=payload.title.strip(),
            body=payload.body.strip(),
            actor=actor,
            user_ids=payload.user_ids if payload.audience == "selected" else None,
            data=payload.data,
        )
        return {"ok": True, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin push campaign failed: {type(e).__name__}", exc_info=True)
        raise HTTPException(status_code=502, detail="Push notification delivery failed")


@admin_router.get("/history")
async def admin_push_history(
    limit: int = Query(default=50, ge=1, le=100),
    actor: str = Depends(require_internal_admin),
):
    return {"ok": True, "data": notification_service.history(limit)}
