from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.modules.auth.service import AuthService


def query_result(data):
    result = MagicMock()
    result.data = data
    return result


def profile_client(profile):
    client = MagicMock()
    client.table.return_value.select.return_value.eq.return_value.execute.return_value = query_result(
        [profile] if profile else []
    )
    client.table.return_value.update.return_value.eq.return_value.execute.return_value = query_result(
        [profile] if profile else []
    )
    return client


def auth_client(user_id="user-id"):
    client = MagicMock()
    client.auth.sign_in_with_password.return_value = SimpleNamespace(
        user=SimpleNamespace(id=user_id),
        session=SimpleNamespace(
            access_token="access-token",
            refresh_token="refresh-token",
            expires_in=3600,
        ),
    )
    return client


@pytest.mark.asyncio
async def test_login_uses_admin_client_for_profile_lookup_hidden_by_rls():
    profile = {
        "id": "user-id",
        "email": "student@example.com",
        "personal_email": "personal@example.com",
        "first_name": "Test",
        "last_name": "Student",
        "university": "Test University",
        "verification_status": "approved",
        "verification_rejection_reason": None,
    }
    admin = profile_client(profile)
    auth = auth_client()
    with (
        patch("app.modules.auth.service.get_user_client", side_effect=AssertionError("RLS client used")),
        patch("app.modules.auth.service.get_supabase_client", return_value=admin),
        patch("app.modules.auth.service.create_fresh_supabase_client", return_value=auth),
        patch("app.modules.auth.service.mark_login"),
    ):
        result = await AuthService().login(
            "student@example.com", "password", device_id="device-id"
        )
    assert result["access_token"] == "access-token"
    assert result["refresh_token"] == "refresh-token"
    assert result["expires_in"] == 3600
    assert result["user"] == {
        "id": "user-id",
        "email": "student@example.com",
        "personal_email": "personal@example.com",
        "first_name": "Test",
        "last_name": "Student",
        "university": "Test University",
    }
    admin.table.return_value.select.return_value.eq.assert_called_with(
        "email", "student@example.com"
    )
    admin.table.return_value.update.return_value.eq.assert_called_with("id", "user-id")
    auth.auth.sign_in_with_password.assert_called_once_with(
        {"email": "student@example.com", "password": "password"}
    )


@pytest.mark.asyncio
async def test_login_reports_missing_account_only_when_admin_lookup_is_empty():
    admin = profile_client(None)
    auth = auth_client()
    with (
        patch("app.modules.auth.service.get_supabase_client", return_value=admin),
        patch("app.modules.auth.service.create_fresh_supabase_client", return_value=auth),
    ):
        with pytest.raises(HTTPException) as exc:
            await AuthService().login("missing@example.com", "password")
    assert exc.value.status_code == 404
    assert "No account found" in str(exc.value.detail)
    auth.auth.sign_in_with_password.assert_not_called()


@pytest.mark.asyncio
async def test_login_rejects_profile_and_auth_id_mismatch():
    profile = {
        "id": "profile-id",
        "email": "student@example.com",
        "personal_email": "personal@example.com",
        "verification_status": "approved",
        "verification_rejection_reason": None,
    }
    admin = profile_client(profile)
    with (
        patch("app.modules.auth.service.get_supabase_client", return_value=admin),
        patch(
            "app.modules.auth.service.create_fresh_supabase_client",
            return_value=auth_client("different-auth-id"),
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            await AuthService().login("student@example.com", "password")
    assert exc.value.status_code == 500
    assert exc.value.detail == "Account data is inconsistent. Please contact support."
    admin.table.return_value.update.assert_not_called()


@pytest.mark.asyncio
async def test_manual_signup_status_uses_admin_client_and_returns_rejection():
    admin = MagicMock()
    admin.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = query_result([
        {
            "email": "student@example.com",
            "verification_status": "rejected",
            "verification_rejection_reason": "Document is unreadable",
        }
    ])
    with (
        patch("app.modules.auth.service.get_user_client", side_effect=AssertionError("RLS client used")),
        patch("app.modules.auth.service.get_supabase_client", return_value=admin),
    ):
        result = await AuthService().get_manual_signup_status("student@example.com")
    assert result["verification_status"] == "rejected"
    assert result["review_reason"] == "Document is unreadable"


@pytest.mark.asyncio
async def test_analytics_uses_admin_client_for_rls_protected_rows():
    redemptions = MagicMock()
    redemptions.select.return_value.eq.return_value.eq.return_value.execute.return_value = query_result([
        {"discount_amount": "20", "total_bill_amount": "100", "final_amount": "80"},
        {"discount_amount": "5", "total_bill_amount": "50", "final_amount": "45"},
    ])
    users = MagicMock()
    users.select.return_value.eq.return_value.execute.return_value = query_result([
        {"account_type": "pro"}
    ])
    admin = MagicMock()
    admin.table.side_effect = lambda table: redemptions if table == "redemptions" else users
    with (
        patch("app.modules.auth.service.get_user_client", side_effect=AssertionError("RLS client used")),
        patch("app.modules.auth.service.get_supabase_client", return_value=admin),
    ):
        result = await AuthService().get_user_analytics("user-id")
    assert result.total_redemptions == 2
    assert result.total_saved == 25
    assert result.total_spent == 150
    assert result.subscription_status == "pro"


@pytest.mark.asyncio
async def test_analytics_returns_zero_values_when_admin_client_is_unavailable():
    with patch("app.modules.auth.service.get_supabase_client", return_value=None):
        result = await AuthService().get_user_analytics("user-id")
    assert result.total_redemptions == 0
    assert result.total_saved == 0
    assert result.total_spent == 0
