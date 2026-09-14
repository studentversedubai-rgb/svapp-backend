import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.security import get_current_user, get_optional_user, get_current_user_no_device_check


@pytest.fixture
def test_secret():
    return "test_jwt_secret_key_12345678901234567890"


@pytest.fixture
def mock_settings(test_secret):
    with patch.object(settings, "SUPABASE_JWT_SECRET", test_secret):
        with patch.object(settings, "JWT_SECRET", test_secret):
            yield


def create_token(payload: dict, secret: str) -> str:
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.mark.asyncio
async def test_valid_token_decodes_successfully(mock_settings, test_secret):
    """Valid JWT should decode locally and retrieve the user from database"""
    user_id = "11111111-2222-3333-4444-555555555555"
    token = create_token({
        "sub": user_id,
        "aud": "authenticated",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "email": "student@university.ae"
    }, test_secret)

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    mock_request = MagicMock()
    mock_request.headers.get.return_value = None

    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": user_id, "email": "student@university.ae", "verification_status": "approved"}
    ]

    with patch("app.core.security.get_supabase_client", return_value=mock_supabase):
        user = await get_current_user(mock_request, credentials)
        assert user["id"] == user_id
        assert user["email"] == "student@university.ae"


@pytest.mark.asyncio
async def test_expired_token_raises_401(mock_settings, test_secret):
    """Expired JWT should raise 401 Unauthorized"""
    user_id = "11111111-2222-3333-4444-555555555555"
    token = create_token({
        "sub": user_id,
        "aud": "authenticated",
        "exp": datetime.now(timezone.utc) - timedelta(minutes=10) # Expired 10 min ago
    }, test_secret)

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    mock_request = MagicMock()

    with patch("app.core.security.get_supabase_client", return_value=MagicMock()):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, credentials)
        assert exc_info.value.status_code == 401
        assert "Invalid or expired token" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_invalid_signature_raises_401(mock_settings):
    """JWT signed with wrong secret key should raise 401"""
    token = create_token({
        "sub": "some-user-id",
        "aud": "authenticated",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1)
    }, "wrong_unauthorized_secret_key_99999")

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    mock_request = MagicMock()

    with patch("app.core.security.get_supabase_client", return_value=MagicMock()):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, credentials)
        assert exc_info.value.status_code == 401
        assert "Invalid or expired token" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_invalid_audience_raises_401(mock_settings, test_secret):
    """JWT with wrong audience should raise 401"""
    token = create_token({
        "sub": "some-user-id",
        "aud": "wrong_audience",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1)
    }, test_secret)

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    mock_request = MagicMock()

    with patch("app.core.security.get_supabase_client", return_value=MagicMock()):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, credentials)
        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_missing_sub_raises_401(mock_settings, test_secret):
    """JWT without 'sub' claim should raise 401"""
    token = create_token({
        "aud": "authenticated",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1)
    }, test_secret)

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    mock_request = MagicMock()

    with patch("app.core.security.get_supabase_client", return_value=MagicMock()):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, credentials)
        assert exc_info.value.status_code == 401
        assert "Invalid token payload" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_get_optional_user_returns_none_for_invalid_token(mock_settings):
    """get_optional_user should return None instead of raising for invalid token"""
    mock_request = MagicMock()
    mock_request.headers.get.return_value = "Bearer invalid_garbage_token"

    with patch("app.core.security.get_supabase_client", return_value=MagicMock()):
        user = await get_optional_user(mock_request)
        assert user is None
