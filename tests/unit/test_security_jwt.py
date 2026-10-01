import hashlib
import hmac
import time

import pytest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from app.core.admin_auth import require_internal_admin
from app.core.security import get_current_user, get_optional_user, get_current_user_no_device_check


def auth_response(user_id="11111111-2222-3333-4444-555555555555", email="student@university.ae"):
    return SimpleNamespace(user=SimpleNamespace(id=user_id, email=email))


@pytest.mark.asyncio
async def test_valid_modern_supabase_token_retrieves_user_profile():
    """Supabase Auth validates the project's active signing algorithm."""
    user_id = "11111111-2222-3333-4444-555555555555"
    token = "es256-access-token"
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    mock_request = MagicMock()
    mock_request.headers.get.return_value = None

    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.return_value = auth_response(user_id)
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": user_id, "email": "student@university.ae", "verification_status": "approved"}
    ]

    with patch("app.core.security.get_supabase_client", return_value=mock_supabase):
        user = await get_current_user(mock_request, credentials)
        assert user["id"] == user_id
        assert user["email"] == "student@university.ae"
    mock_supabase.auth.get_user.assert_called_once_with(token)


@pytest.mark.asyncio
async def test_expired_token_raises_401():
    """An expired token rejected by Supabase Auth returns 401."""
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="expired-token")
    mock_request = MagicMock()
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.side_effect = Exception("expired")

    with patch("app.core.security.get_supabase_client", return_value=mock_supabase):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, credentials)
        assert exc_info.value.status_code == 401
        assert "Invalid or expired token" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_invalid_signature_raises_401():
    """A token with an invalid signature is rejected by Supabase Auth."""
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid-token")
    mock_request = MagicMock()
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.side_effect = Exception("invalid signature")

    with patch("app.core.security.get_supabase_client", return_value=mock_supabase):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, credentials)
        assert exc_info.value.status_code == 401
        assert "Invalid or expired token" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_token_rejected_by_auth_service_raises_401():
    """Audience and issuer checks are delegated to Supabase Auth."""
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong-audience")
    mock_request = MagicMock()
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.side_effect = Exception("wrong audience")

    with patch("app.core.security.get_supabase_client", return_value=mock_supabase):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, credentials)
        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_missing_auth_user_id_raises_401():
    """A validation response without a user id cannot authenticate."""
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="missing-user")
    mock_request = MagicMock()
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.return_value = auth_response(user_id=None)

    with patch("app.core.security.get_supabase_client", return_value=mock_supabase):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, credentials)
        assert exc_info.value.status_code == 401
        assert "Invalid token payload" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_get_optional_user_returns_none_for_invalid_token():
    """get_optional_user should return None instead of raising for invalid token"""
    mock_request = MagicMock()
    mock_request.headers.get.return_value = "Bearer invalid_garbage_token"
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.side_effect = Exception("invalid token")

    with patch("app.core.security.get_supabase_client", return_value=mock_supabase):
        user = await get_optional_user(mock_request)
        assert user is None


@pytest.mark.asyncio
async def test_no_device_check_accepts_modern_supabase_token():
    """Registration auth uses the same algorithm-aware validation path."""
    user_id = "11111111-2222-3333-4444-555555555555"
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="es256-token")
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.return_value = auth_response(user_id)
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []

    with patch("app.core.security.get_supabase_client", return_value=mock_supabase):
        user = await get_current_user_no_device_check(credentials)
    assert user == {"id": user_id, "email": "student@university.ae"}


@pytest.mark.asyncio
async def test_internal_admin_accepts_service_key_signature():
    service_key = "shared-service-key"
    timestamp = str(int(time.time()))
    signature = hmac.new(service_key.encode(), timestamp.encode(), hashlib.sha256).hexdigest()
    settings = SimpleNamespace(ADMIN_API_TOKEN="", SUPABASE_SERVICE_KEY=service_key)

    with patch("app.core.admin_auth.Settings", return_value=settings):
        actor = await require_internal_admin(
            x_admin_token="",
            x_admin_actor="dashboard",
            x_admin_timestamp=timestamp,
            x_admin_signature=signature,
        )

    assert actor == "dashboard"


@pytest.mark.asyncio
async def test_internal_admin_rejects_expired_service_key_signature():
    service_key = "shared-service-key"
    timestamp = str(int(time.time()) - 61)
    signature = hmac.new(service_key.encode(), timestamp.encode(), hashlib.sha256).hexdigest()
    settings = SimpleNamespace(ADMIN_API_TOKEN="", SUPABASE_SERVICE_KEY=service_key)

    with patch("app.core.admin_auth.Settings", return_value=settings):
        with pytest.raises(HTTPException) as exc_info:
            await require_internal_admin(
                x_admin_token="",
                x_admin_actor="dashboard",
                x_admin_timestamp=timestamp,
                x_admin_signature=signature,
            )

    assert exc_info.value.status_code == 401
