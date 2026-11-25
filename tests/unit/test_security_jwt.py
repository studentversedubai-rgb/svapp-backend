import hashlib
import hmac
import time

import pytest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt
from app.core.config import get_settings
from app.core.admin_auth import require_internal_admin
from app.core.security import get_current_user, get_optional_user, get_current_user_no_device_check
from app.core.jwt_utils import create_access_token


@pytest.mark.asyncio
async def test_valid_token_retrieves_user_profile():
    """Valid JWT token decodes and retrieves the user from DB."""
    user_id = "11111111-2222-3333-4444-555555555555"
    token = create_access_token(user_id, "student@university.ae")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    mock_request = MagicMock()
    mock_request.headers.get.return_value = None

    profile = {"id": user_id, "email": "student@university.ae", "verification_status": "approved", "device_id": None}

    with patch("app.core.security.fetch_one", return_value=profile):
        user = await get_current_user(mock_request, credentials)
        assert user["id"] == user_id
        assert user["email"] == "student@university.ae"


@pytest.mark.asyncio
async def test_expired_token_raises_401():
    """An expired token returns 401."""
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="expired-token")
    mock_request = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(mock_request, credentials)
    assert exc_info.value.status_code == 401
    assert "Invalid or expired token" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_invalid_signature_raises_401():
    """A token with an invalid signature is rejected."""
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid-token")
    mock_request = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(mock_request, credentials)
    assert exc_info.value.status_code == 401
    assert "Invalid or expired token" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_missing_auth_user_id_raises_401():
    """A token without subject id cannot authenticate."""
    settings = get_settings()
    token = jwt.encode({"email": "student@university.ae"}, settings.JWT_SECRET, algorithm="HS256")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    mock_request = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(mock_request, credentials)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_optional_user_returns_none_for_invalid_token():
    """get_optional_user should return None instead of raising for invalid token."""
    mock_request = MagicMock()
    mock_request.headers.get.return_value = "Bearer invalid_garbage_token"

    user = await get_optional_user(mock_request)
    assert user is None


@pytest.mark.asyncio
async def test_no_device_check_accepts_valid_token():
    """Registration auth validates token without requiring device match."""
    user_id = "11111111-2222-3333-4444-555555555555"
    token = create_access_token(user_id, "student@university.ae")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    profile = {"id": user_id, "email": "student@university.ae"}
    with patch("app.core.security.fetch_one", return_value=profile):
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
