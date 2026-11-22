import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import dotenv
import pytest


@pytest.fixture
def database(monkeypatch):
    monkeypatch.setattr(dotenv, "load_dotenv", lambda: False)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sb_secret_test_only")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "sb_publishable_test_only")
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    path = Path(__file__).parents[2] / "app" / "core" / "database.py"
    spec = importlib.util.spec_from_file_location("database_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sdk_accepts_secret_and_publishable_keys(database):
    assert database.get_supabase_client() is not None
    assert database.get_user_client() is not None
    assert database.create_fresh_supabase_client() is not None


def test_auth_clients_are_isolated_from_admin(database):
    first = database.create_fresh_supabase_client()
    second = database.create_fresh_supabase_client()
    assert first is not None
    assert first is not second
    assert first is not database.get_supabase_client()
    assert first.options.headers["apiKey"] == "sb_publishable_test_only"
    assert database.get_supabase_client().options.headers["apiKey"] == "sb_secret_test_only"


def test_publishable_key_cannot_be_used_as_admin_key(database, monkeypatch):
    monkeypatch.setattr(database, "_supabase_service_key", "sb_publishable_test_only")
    assert database._build_admin_client() is None


def test_secret_key_cannot_be_used_for_rls_client(database, monkeypatch):
    monkeypatch.setattr(database, "_supabase_anon_key", "sb_secret_test_only")
    assert database.get_user_client() is None
    assert database.create_fresh_supabase_client() is None


def test_failed_client_initialization_never_logs_key(database, monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise ValueError("Rejected sb_secret_sensitive_test_value")

    monkeypatch.setattr(database, "create_client", fail)
    capsys.readouterr()
    assert database._build_admin_client() is None
    output = capsys.readouterr()
    assert "sb_secret_sensitive_test_value" not in output.out + output.err


def test_database_readiness_checks_both_key_roles(database, monkeypatch):
    admin = MagicMock()
    public = MagicMock()
    monkeypatch.setattr(database, "_admin_client", admin)
    monkeypatch.setattr(database, "get_user_client", lambda: public)
    database.validate_database_configuration()
    for client in (admin, public):
        client.table.assert_called_once_with("categories")
        client.table.return_value.select.return_value.limit.return_value.execute.assert_called_once()


def test_database_readiness_rejects_missing_admin(database, monkeypatch):
    monkeypatch.setattr(database, "_admin_client", None)
    with pytest.raises(RuntimeError, match="SUPABASE_SERVICE_KEY"):
        database.validate_database_configuration()


def test_database_readiness_rejects_missing_public_client(database, monkeypatch):
    monkeypatch.setattr(database, "_admin_client", MagicMock())
    monkeypatch.setattr(database, "get_user_client", lambda: None)
    with pytest.raises(RuntimeError, match="SUPABASE_ANON_KEY"):
        database.validate_database_configuration()


def test_database_readiness_rejects_unusable_keys_without_exposing_them(database, monkeypatch):
    admin = MagicMock()
    admin.table.return_value.select.return_value.limit.return_value.execute.side_effect = ValueError(
        "Invalid sb_secret_sensitive_test_value"
    )
    monkeypatch.setattr(database, "_admin_client", admin)
    monkeypatch.setattr(database, "get_user_client", MagicMock())
    with pytest.raises(RuntimeError, match="database readiness") as exc:
        database.validate_database_configuration()
    assert "sb_secret_sensitive_test_value" not in str(exc.value)


@pytest.fixture
def backend(database, monkeypatch):
    from app import main

    monkeypatch.setattr(main, "validate_database_configuration", MagicMock())
    monkeypatch.setattr(main.redis_manager, "connect", MagicMock())
    monkeypatch.setattr(main.redis_manager, "is_ready", MagicMock(return_value=True))
    return main


@pytest.mark.asyncio
async def test_health_fails_when_database_is_unavailable(backend):
    backend.validate_database_configuration.side_effect = RuntimeError("Invalid API key")
    response = await backend.health()
    assert response.status_code == 503
    assert json.loads(response.body)["checks"]["database"] is False
    assert "Invalid API key" not in response.body.decode()


@pytest.mark.asyncio
async def test_health_fails_when_redis_is_unavailable(backend):
    backend.redis_manager.is_ready.return_value = False
    response = await backend.health()
    assert response.status_code == 503
    assert json.loads(response.body)["checks"]["redis"] is False


@pytest.mark.asyncio
async def test_health_passes_when_dependencies_are_ready(backend):
    response = await backend.health()
    assert response.status_code == 200
    assert json.loads(response.body)["status"] == "ok"


@pytest.mark.asyncio
async def test_health_reports_postmark_and_stripe_configuration(backend, monkeypatch):
    monkeypatch.setattr(
        backend,
        "get_settings",
        lambda: SimpleNamespace(
            POSTMARK_API_KEY="postmark-token",
            REVIEW_FROM_ADDRESS="verified@example.com",
            STRIPE_SECRET_KEY="stripe-key",
            STRIPE_WEBHOOK_SECRET="webhook-secret",
        ),
    )
    response = await backend.health()
    body = json.loads(response.body)
    assert body["integrations"] == {"postmark": True, "stripe": True}


@pytest.mark.asyncio
async def test_health_reports_unconfigured_optional_integrations(backend, monkeypatch):
    monkeypatch.setattr(
        backend,
        "get_settings",
        lambda: SimpleNamespace(
            POSTMARK_API_KEY="",
            REVIEW_FROM_ADDRESS="verified@example.com",
            STRIPE_SECRET_KEY="",
            STRIPE_WEBHOOK_SECRET="",
        ),
    )
    response = await backend.health()
    body = json.loads(response.body)
    assert body["integrations"] == {"postmark": False, "stripe": False}
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_startup_stops_before_serving_requests_with_no_database(backend):
    backend.validate_database_configuration.side_effect = RuntimeError("Database unavailable")
    with pytest.raises(RuntimeError, match="Database unavailable"):
        await backend.create_app().router.startup()
    backend.redis_manager.connect.assert_not_called()


@pytest.mark.asyncio
async def test_startup_requires_redis_after_validating_database(backend):
    backend.redis_manager.connect.side_effect = RuntimeError("Redis unavailable")
    with pytest.raises(RuntimeError, match="Redis unavailable"):
        await backend.create_app().router.startup()
    backend.validate_database_configuration.assert_called_once()
