from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.auth.service import AuthService
from app.modules.notifications.router import (
    AdminPushRequest,
    ApplicationPushTokenRegister,
    register_application_push_token,
)
from app.modules.notifications.service import NotificationService


class FakeHttpClient:
    def __init__(self, tickets):
        self.tickets = tickets
        self.post = AsyncMock(return_value=SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"data": self.tickets},
        ))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


def database_with_tokens(tokens):
    token_table = MagicMock()
    token_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(data=tokens)
    token_table.select.return_value.eq.return_value.in_.return_value.execute.return_value = SimpleNamespace(data=tokens)
    token_table.update.return_value.in_.return_value.execute.return_value = SimpleNamespace(data=[])
    analytics_table = MagicMock()
    analytics_table.insert.return_value.execute.return_value = SimpleNamespace(data=[{"id": "event-id"}])
    database = MagicMock()
    database.table.side_effect = lambda name: token_table if name == "user_push_tokens" else analytics_table
    return database, token_table, analytics_table


@pytest.mark.asyncio
async def test_push_campaign_sends_enabled_unique_expo_tokens_and_logs_history():
    tokens = [
        {"id": "1", "user_id": "u1", "expo_push_token": "ExponentPushToken[token-1]", "device_platform": "ios"},
        {"id": "2", "user_id": "u1", "expo_push_token": "ExponentPushToken[token-1]", "device_platform": "ios"},
        {"id": "3", "user_id": "u2", "expo_push_token": "not-an-expo-token", "device_platform": "web"},
        {"id": "4", "user_id": "u3", "expo_push_token": "ExpoPushToken[token-2]", "device_platform": "android"},
    ]
    database, _, analytics = database_with_tokens(tokens)
    service = NotificationService()
    service.supabase = database
    http = FakeHttpClient([{"status": "ok"}, {"status": "ok"}])
    with (
        patch("app.modules.notifications.service.httpx.AsyncClient", return_value=http),
        patch(
            "app.modules.notifications.service.get_settings",
            return_value=SimpleNamespace(EXPO_ACCESS_TOKEN="expo-access-token"),
        ),
    ):
        result = await service.send_campaign(
            title="New student deal",
            body="A verified offer is now live.",
            actor="dashboard-admin",
            data={"screen": "offers"},
        )
    assert result["target_count"] == 2
    assert result["sent_count"] == 2
    assert result["failed_count"] == 0
    messages = http.post.call_args.kwargs["json"]
    assert http.post.call_args.kwargs["headers"]["Authorization"] == "Bearer expo-access-token"
    assert {message["to"] for message in messages} == {
        "ExponentPushToken[token-1]",
        "ExpoPushToken[token-2]",
    }
    logged = analytics.insert.call_args.args[0]
    assert logged["event_type"] == "admin_push_notification"
    assert logged["event_data"]["actor"] == "dashboard-admin"


@pytest.mark.asyncio
async def test_unregistered_device_token_is_disabled():
    tokens = [
        {"id": "1", "user_id": "u1", "expo_push_token": "ExponentPushToken[dead]", "device_platform": "ios"}
    ]
    database, token_table, _ = database_with_tokens(tokens)
    service = NotificationService()
    service.supabase = database
    http = FakeHttpClient([
        {"status": "error", "details": {"error": "DeviceNotRegistered"}}
    ])
    with patch("app.modules.notifications.service.httpx.AsyncClient", return_value=http):
        result = await service.send_campaign(title="Test", body="Body", actor="admin")
    assert result["failed_count"] == 1
    token_table.update.return_value.in_.assert_called_once_with(
        "expo_push_token", ["ExponentPushToken[dead]"]
    )


def test_selected_audience_requires_user_ids():
    with pytest.raises(ValueError):
        AdminPushRequest(title="Title", body="Body", audience="selected", user_ids=[])


def test_all_audience_rejects_hidden_user_filter():
    with pytest.raises(ValueError):
        AdminPushRequest(title="Title", body="Body", audience="all", user_ids=["u1"])


@pytest.mark.asyncio
async def test_pending_application_can_register_push_token_with_one_time_token():
    database = MagicMock()
    table = database.table.return_value
    table.select.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(data=[])
    table.insert.return_value.execute.return_value = SimpleNamespace(data=[{"id": "push-id"}])
    payload = ApplicationPushTokenRegister(
        registration_token="registration-token",
        token="ExponentPushToken[test]",
        platform="ios",
    )
    with (
        patch("app.modules.notifications.router.redis_manager.get", return_value="user-id"),
        patch("app.modules.notifications.router.redis_manager.delete") as delete,
        patch("app.modules.notifications.router.get_supabase_client", return_value=database),
    ):
        result = await register_application_push_token(payload)
    assert result["success"] is True
    table.insert.assert_called_once_with({
        "user_id": "user-id",
        "expo_push_token": "ExponentPushToken[test]",
        "device_platform": "ios",
        "is_enabled": True,
    })
    delete.assert_called_once_with("sv:app:auth:push_registration:registration-token")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("approved", "title", "status"),
    [
        (True, "WELCOME TO THE SV FAMILY!", "approved"),
        (False, "Application update needed", "rejected"),
    ],
)
async def test_review_decision_push_copy(approved, title, status):
    with patch(
        "app.modules.auth.service.notification_service.send_campaign",
        new_callable=AsyncMock,
    ) as send:
        await AuthService()._send_review_push("user-id", approved=approved)
    assert send.await_args.kwargs["title"] == title
    assert send.await_args.kwargs["user_ids"] == ["user-id"]
    assert send.await_args.kwargs["data"]["status"] == status
