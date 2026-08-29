from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
# Fixed imports: core/database exports get_supabase_client() and core/security exports get_current_user()
from app.core.database import get_supabase_client
from app.core.security import get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/push-tokens", tags=["notifications"])


class PushTokenRegister(BaseModel):
    userId: str
    token: str
    platform: str


class PushTokenUpdate(BaseModel):
    token: str
    platform: str
    isEnabled: Optional[bool] = True


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
        # Verify the requesting user matches the userId in payload
        if payload.userId != current_user_id:
            raise HTTPException(status_code=403, detail="Cannot register token for another user")

        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(status_code=500, detail="Database connection unavailable")

        # Check if token already exists for this user
        response = supabase.table("user_push_tokens").select("id").eq(
            "user_id", payload.userId
        ).eq("expo_push_token", payload.token).execute()

        if response.data and len(response.data) > 0:
            # Token exists, update it
            token_id = response.data[0]["id"]
            update_response = supabase.table("user_push_tokens").update(
                {
                    "device_platform": payload.platform,
                    "is_enabled": True,
                    "updated_at": "now()",
                }
            ).eq("id", token_id).execute()

            if getattr(update_response, "error", None):
                logger.error(f"Error updating push token: {update_response.error}")
                raise HTTPException(status_code=500, detail="Failed to update push token")

            logger.info(f"Updated push token for user {payload.userId}")
            return {"success": True, "message": "Push token updated", "tokenId": token_id}
        else:
            # Create new token entry
            insert_response = supabase.table("user_push_tokens").insert(
                {
                    "user_id": payload.userId,
                    "expo_push_token": payload.token,
                    "device_platform": payload.platform,
                    "is_enabled": True,
                }
            ).execute()

            if getattr(insert_response, "error", None):
                logger.error(f"Error inserting push token: {insert_response.error}")
                raise HTTPException(status_code=500, detail="Failed to register push token")

            token_id = insert_response.data[0]["id"] if insert_response.data else None
            logger.info(f"Registered new push token for user {payload.userId}")
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

        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(status_code=500, detail="Database connection unavailable")

        # Update the token
        response = supabase.table("user_push_tokens").update(
            {
                "expo_push_token": payload.token,
                "device_platform": payload.platform,
                "is_enabled": payload.isEnabled,
                "updated_at": "now()",
            }
        ).eq("user_id", user_id).execute()

        if getattr(response, "error", None):
            logger.error(f"Error updating push token: {response.error}")
            raise HTTPException(status_code=500, detail="Failed to update push token")

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

        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(status_code=500, detail="Database connection unavailable")

        # Soft delete by disabling
        response = supabase.table("user_push_tokens").update(
            {"is_enabled": False, "updated_at": "now()"}
        ).eq("user_id", user_id).execute()

        if getattr(response, "error", None):
            logger.error(f"Error deleting push token: {response.error}")
            raise HTTPException(status_code=500, detail="Failed to delete push token")

        return {"success": True, "message": "Push token disabled"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting push token: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
