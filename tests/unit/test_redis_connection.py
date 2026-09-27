import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import dotenv
import pytest
import redis


@pytest.fixture
def redis_module(monkeypatch):
    monkeypatch.setattr(dotenv, "load_dotenv", lambda: False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)
    path = Path(__file__).parents[2] / "app" / "core" / "redis.py"
    spec = importlib.util.spec_from_file_location("redis_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unavailable_redis(monkeypatch):
    client = MagicMock()
    client.ping.side_effect = redis.ConnectionError("Connection refused")
    monkeypatch.setattr(redis, "from_url", lambda *args, **kwargs: client)
    return client


def test_local_development_can_use_memory(redis_module, monkeypatch):
    unavailable_redis(monkeypatch)
    manager = redis_module.RedisManager()
    manager.connect()
    assert manager.redis_client is None
    assert manager.is_ready()
    manager.setex("proof", 30, "test-token")
    assert manager.get("proof") == "test-token"


@pytest.mark.parametrize("deployment", ["production", "railway"])
def test_deployed_service_requires_shared_redis(redis_module, monkeypatch, deployment):
    if deployment == "production":
        monkeypatch.setenv("ENVIRONMENT", "production")
    else:
        monkeypatch.setenv("RAILWAY_PROJECT_ID", "test-project")
    unavailable_redis(monkeypatch)
    manager = redis_module.RedisManager()
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        manager.connect()
    assert not manager.is_ready()


def test_redis_health_tracks_connectivity(redis_module, monkeypatch):
    client = MagicMock()
    client.ping.return_value = True
    monkeypatch.setattr(redis, "from_url", lambda *args, **kwargs: client)
    manager = redis_module.RedisManager()
    manager.connect()
    assert manager.is_ready()
    client.ping.side_effect = redis.ConnectionError("Connection refused")
    assert not manager.is_ready()


def test_memory_storage_never_logs_redemption_tokens(redis_module, capsys):
    manager = redis_module.RedisManager()
    manager.setex("qr:private-test-key", 30, "private-test-token")
    output = capsys.readouterr()
    assert "private-test-token" not in output.out + output.err
    assert "private-test-key" not in output.out + output.err
