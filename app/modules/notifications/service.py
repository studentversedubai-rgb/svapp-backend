import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

import httpx

from app.core.database import get_supabase_client
from app.core.config import get_settings

logger = logging.getLogger(__name__)
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
EXPO_BATCH_SIZE = 100


def _chunks(values: list, size: int) -> Iterable[list]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _is_expo_token(value: str) -> bool:
    return value.startswith("ExponentPushToken[") or value.startswith("ExpoPushToken[")


class NotificationService:
    def __init__(self):
        self.supabase = get_supabase_client()

    def _require_database(self):
        if not self.supabase:
            raise RuntimeError("Database connection unavailable")
        return self.supabase

    def get_tokens(self, user_ids: Optional[list[str]] = None) -> list[dict]:
        query = (
            self._require_database()
            .table("user_push_tokens")
            .select("id,user_id,push_token,platform")
        )
        if user_ids:
            query = query.in_("user_id", user_ids)
        response = query.execute()
        unique: Dict[str, dict] = {}
        for row in response.data or []:
            token = str(row.get("push_token") or "")
            if _is_expo_token(token):
                unique[token] = row
        return list(unique.values())

    async def send_campaign(
        self,
        *,
        title: str,
        body: str,
        actor: str,
        user_ids: Optional[list[str]] = None,
        data: Optional[Dict[str, Any]] = None,
        log_event: bool = True,
    ) -> dict:
        tokens = self.get_tokens(user_ids)
        messages = [
            {
                "to": row["push_token"],
                "sound": "default",
                "title": title,
                "body": body,
                "data": data or {},
                "priority": "high",
            }
            for row in tokens
        ]
        sent = 0
        failed = 0
        invalid_tokens: list[str] = []

        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        access_token = get_settings().EXPO_ACCESS_TOKEN
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        async with httpx.AsyncClient(timeout=20.0) as client:
            for batch in _chunks(messages, EXPO_BATCH_SIZE):
                response = await client.post(
                    EXPO_PUSH_URL,
                    json=batch,
                    headers=headers,
                )
                response.raise_for_status()
                tickets = response.json().get("data") or []
                for message, ticket in zip(batch, tickets):
                    if ticket.get("status") == "ok":
                        sent += 1
                    else:
                        failed += 1
                        if (ticket.get("details") or {}).get("error") == "DeviceNotRegistered":
                            invalid_tokens.append(message["to"])
                if len(tickets) < len(batch):
                    failed += len(batch) - len(tickets)

        if invalid_tokens:
            self._require_database().table("user_push_tokens").delete().in_(
                "push_token", invalid_tokens
            ).execute()

        event_data = {
            "title": title,
            "body": body,
            "actor": actor,
            "audience": "selected" if user_ids else "all",
            "requested_user_count": len(user_ids or []),
            "target_count": len(messages),
            "sent_count": sent,
            "failed_count": failed,
            "data": data or {},
        }
        if log_event:
            self._require_database().table("analytics_events").insert(
                {"event_type": "admin_push_notification", "event_data": event_data}
            ).execute()
        return event_data

    async def process_scheduled_campaigns(
        self, now: Optional[datetime] = None
    ) -> int:
        now = now or datetime.now(timezone.utc)
        response = (
            self._require_database()
            .table("analytics_events")
            .select("id,event_data,created_at")
            .eq("event_type", "scheduled_push_notification")
            .order("created_at")
            .limit(100)
            .execute()
        )
        processed = 0
        for row in response.data or []:
            event_data = dict(row.get("event_data") or {})
            if event_data.get("status") != "scheduled":
                continue
            try:
                scheduled_for = datetime.fromisoformat(
                    str(event_data.get("scheduled_for") or "").replace("Z", "+00:00")
                )
            except ValueError:
                continue
            if scheduled_for.tzinfo is None:
                scheduled_for = scheduled_for.replace(tzinfo=timezone.utc)
            if scheduled_for > now:
                continue

            event_data["status"] = "processing"
            self._require_database().table("analytics_events").update(
                {"event_data": event_data}
            ).eq("id", row["id"]).execute()
            try:
                result = await self.send_campaign(
                    title=str(event_data.get("title") or ""),
                    body=str(event_data.get("body") or ""),
                    actor=str(event_data.get("actor") or "scheduler"),
                    user_ids=event_data.get("user_ids") or None,
                    data=event_data.get("data") or {},
                    log_event=False,
                )
                delivered = result["target_count"] > 0
                event_data.update(
                    {
                        "status": "sent" if delivered else "failed",
                        "sent_at": now.isoformat() if delivered else None,
                        "failed_at": None if delivered else now.isoformat(),
                        "failure_reason": None if delivered else "no_registered_devices",
                        "target_count": result["target_count"],
                        "sent_count": result["sent_count"],
                        "failed_count": result["failed_count"],
                    }
                )
                if delivered:
                    processed += 1
            except Exception as exc:
                logger.error(
                    "Scheduled push campaign %s failed: %s", row["id"], type(exc).__name__
                )
                event_data.update(
                    {"status": "failed", "failed_at": now.isoformat()}
                )
            self._require_database().table("analytics_events").update(
                {"event_data": event_data}
            ).eq("id", row["id"]).execute()
        return processed

    def history(self, limit: int = 50) -> list[dict]:
        response = (
            self._require_database()
            .table("analytics_events")
            .select("id,event_data,created_at")
            .in_("event_type", ["admin_push_notification", "scheduled_push_notification"])
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data or []


notification_service = NotificationService()


async def scheduled_push_worker() -> None:
    while True:
        try:
            await notification_service.process_scheduled_campaigns()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Scheduled push worker failed: %s", type(exc).__name__)
        await asyncio.sleep(30)
