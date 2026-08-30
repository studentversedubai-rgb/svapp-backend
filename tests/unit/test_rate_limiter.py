"""
Unit tests for the request rate limiter.

Regression coverage for the permanent-lockout bug: a bare Redis INCR on a key
that expired between GET and INCR recreated it without a TTL, so the counter
climbed past the limit and never reset - users stayed 429'd no matter how long
they waited.
"""

import time

import pytest
from fastapi import HTTPException

from app.core.redis import redis_manager
from app.middleware.ratelimit import RateLimiter, RateLimitMiddleware


class FakeRedis:
    """Minimal Redis stand-in. Rejects EVAL so the pipeline path is exercised."""

    def __init__(self):
        self.counts = {}
        self.ttls = {}

    def script_load(self, script):
        raise Exception("NOSCRIPT")

    def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def ttl(self, key):
        return self.ttls.get(key, -1)

    def expire(self, key, window):
        self.ttls[key] = window
        return True

    def pipeline(self):
        outer = self

        class Pipe:
            def __init__(self):
                self.queued = []

            def incr(self, key):
                self.queued.append(("incr", key))

            def ttl(self, key):
                self.queued.append(("ttl", key))

            def execute(self):
                return [getattr(outer, op)(key) for op, key in self.queued]

        return Pipe()


@pytest.fixture
def fake_redis():
    original = redis_manager.redis_client
    client = FakeRedis()
    redis_manager.redis_client = client
    RateLimiter._lua_sha = None
    yield client
    redis_manager.redis_client = original
    RateLimiter._lua_sha = None


@pytest.fixture
def memory_mode():
    original = redis_manager.redis_client
    redis_manager.redis_client = None
    redis_manager.memory_store.clear()
    yield
    redis_manager.memory_store.clear()
    redis_manager.redis_client = original


def test_allows_exactly_the_limit_then_blocks(memory_mode):
    for _ in range(5):
        RateLimiter.check_generic_limit("k", 5, 60)

    with pytest.raises(HTTPException) as exc:
        RateLimiter.check_generic_limit("k", 5, 60)

    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"]


def test_window_expiry_unblocks(memory_mode):
    for _ in range(3):
        RateLimiter.check_generic_limit("k", 3, 1)
    with pytest.raises(HTTPException):
        RateLimiter.check_generic_limit("k", 3, 1)

    time.sleep(1.1)

    info = RateLimiter.check_generic_limit("k", 3, 1)
    assert info["remaining"] == 2


def test_memory_fallback_keeps_the_ttl_tuple_format(memory_mode):
    """Raw ints here broke _clean_expired_memory_keys and never expired."""
    RateLimiter.check_generic_limit("k", 5, 60)

    value, expiry = redis_manager.memory_store["k"]
    assert value == "1"
    assert expiry > time.time()
    redis_manager._clean_expired_memory_keys()  # must not raise


def test_first_request_always_sets_an_expiry(fake_redis):
    RateLimiter.check_generic_limit("g", 5, 60)
    assert fake_redis.ttls["g"] == 60


def test_ttl_less_key_is_repaired_instead_of_locking_out(fake_redis):
    """The permanent-lockout regression: a key with no TTL must self-heal."""
    RateLimiter.check_generic_limit("g", 5, 60)
    fake_redis.ttls["g"] = -1  # INCR recreated the key without an expiry

    RateLimiter.check_generic_limit("g", 5, 60)

    assert fake_redis.ttls["g"] == 60


def test_fails_open_when_the_backend_breaks(fake_redis):
    def boom(*args, **kwargs):
        raise Exception("redis down")

    fake_redis.pipeline = boom

    info = RateLimiter.check_generic_limit("g", 5, 60)
    assert info["remaining"] == 5


class FakeRequest:
    def __init__(self, headers=None, client_host="10.0.0.1"):
        self.headers = headers or {}
        self.client = type("Client", (), {"host": client_host})()


def test_authenticated_callers_get_their_own_bucket():
    """Two users behind one carrier NAT must not share a limit."""
    mw = RateLimitMiddleware.__new__(RateLimitMiddleware)
    shared_ip = "92.97.207.12"

    a = mw._identity(FakeRequest({"Authorization": "Bearer " + "a" * 40}), shared_ip)
    b = mw._identity(FakeRequest({"Authorization": "Bearer " + "b" * 40}), shared_ip)

    assert a != b
    assert "a" * 40 not in a  # token is hashed, never echoed into a key


def test_anonymous_callers_fall_back_to_ip():
    mw = RateLimitMiddleware.__new__(RateLimitMiddleware)
    assert mw._identity(FakeRequest(), "1.2.3.4") == "ip:1.2.3.4"


def test_forwarded_for_is_read_past_the_trusted_proxy():
    """Leftmost is client-supplied; trusting it lets anyone spoof past the limiter."""
    mw = RateLimitMiddleware.__new__(RateLimitMiddleware)
    mw.PROXY_HOPS = 1

    req = FakeRequest({"X-Forwarded-For": "1.1.1.1, 92.97.207.12"})

    assert mw._get_ip(req) == "92.97.207.12"


def test_falls_back_to_socket_ip_without_forwarded_header():
    mw = RateLimitMiddleware.__new__(RateLimitMiddleware)
    assert mw._get_ip(FakeRequest(client_host="10.0.0.9")) == "10.0.0.9"
