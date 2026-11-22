"""
Database Module

Azure PostgreSQL Flexible Server connection pool.
Uses psycopg2 synchronous driver — compatible with existing service layer.

Migration note: get_supabase_client() and get_user_client() return a
_SupabaseShim that raises NotImplementedError on .table(...).execute().
Migrate each service to use fetch_one/fetch_all/execute directly.
"""

import os
from contextlib import contextmanager
from typing import Dict, List, Optional, Any

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
from dotenv import load_dotenv

load_dotenv()

_DATABASE_URL: str = os.getenv("DATABASE_URL", "").strip()

# ---------------------------------------------------------------------------
# Connection pool — initialised at module load time.
# ---------------------------------------------------------------------------
_pool: Optional[ThreadedConnectionPool] = None


def _build_pool() -> Optional[ThreadedConnectionPool]:
    if not _DATABASE_URL:
        print("WARNING: DATABASE_URL not set — database pool not initialised")
        return None
    try:
        pool = ThreadedConnectionPool(minconn=1, maxconn=10, dsn=_DATABASE_URL)
        print("INFO: Initialised Azure PostgreSQL connection pool")
        return pool
    except Exception as e:
        print(
            f"ERROR: Failed to initialise PostgreSQL connection pool "
            f"({type(e).__name__}: {e})"
        )
        return None


_pool = _build_pool()


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def fetch_one(sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    """Execute *sql* and return the first row as a dict, or None."""
    if _pool is None:
        raise RuntimeError("Database pool is not available. Check DATABASE_URL.")
    conn = _pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row is not None else None
    finally:
        _pool.putconn(conn)


def fetch_all(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """Execute *sql* and return all rows as a list of dicts."""
    if _pool is None:
        raise RuntimeError("Database pool is not available. Check DATABASE_URL.")
    conn = _pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            return [dict(r) for r in rows]
    finally:
        _pool.putconn(conn)


def execute(sql: str, params: tuple = ()) -> int:
    """Execute a DML statement, commit, and return the rowcount."""
    if _pool is None:
        raise RuntimeError("Database pool is not available. Check DATABASE_URL.")
    conn = _pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rowcount = cur.rowcount
        conn.commit()
        return rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def fetch_val(sql: str, params: tuple = ()) -> Any:
    """Return the first column of the first row, or None."""
    if _pool is None:
        raise RuntimeError("Database pool is not available. Check DATABASE_URL.")
    conn = _pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return row[0] if row is not None else None
    finally:
        _pool.putconn(conn)


@contextmanager
def get_db_connection():
    """
    Context manager that yields a raw psycopg2 connection for multi-step
    transactions. The caller is responsible for committing or rolling back.

    Usage::

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(...)
            conn.commit()
    """
    if _pool is None:
        raise RuntimeError("Database pool is not available. Check DATABASE_URL.")
    conn = _pool.getconn()
    try:
        yield conn
    finally:
        _pool.putconn(conn)


def validate_database_configuration() -> None:
    """Run a lightweight SELECT 1 to confirm connectivity. Raises RuntimeError on failure."""
    try:
        result = fetch_val("SELECT 1")
        if result != 1:
            raise RuntimeError("Unexpected result from SELECT 1 health check.")
        print("INFO: Database connectivity validated (SELECT 1 OK)")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(
            f"Database readiness check failed ({type(e).__name__}: {e}). "
            "Verify DATABASE_URL and network connectivity."
        ) from None


# ---------------------------------------------------------------------------
# Supabase compatibility shims
# These keep existing imports from crashing while services are migrated.
# Replace all .table(...).execute() call-sites with fetch_one/fetch_all/execute.
# ---------------------------------------------------------------------------

class _TableQuery:
    """Stub table query object — always raises NotImplementedError on execute()."""

    def __init__(self, table_name: str):
        self._table = table_name

    def __getattr__(self, name):
        # Allow fluent chaining (e.g. .select(...).limit(...)) to reach .execute()
        return self

    def __call__(self, *args, **kwargs):
        return self

    def execute(self):
        raise NotImplementedError(
            f"Migrate this call on table '{self._table}' to "
            "fetch_one / fetch_all / execute from app.core.database"
        )


class _SupabaseShim:
    """Minimal shim so code importing get_supabase_client() doesn't crash on startup."""

    def table(self, name: str) -> _TableQuery:
        return _TableQuery(name)

    # Stub out .auth so attribute access doesn't raise AttributeError
    class _AuthShim:
        def __getattr__(self, name):
            def _raise(*args, **kwargs):
                raise NotImplementedError(
                    f"Supabase auth.{name} is not available after migration. "
                    "Implement the equivalent directly against Azure PostgreSQL."
                )
            return _raise

    auth = _AuthShim()


_shim = _SupabaseShim()


def get_supabase_client() -> _SupabaseShim:
    """
    Compatibility alias — returns a shim object.
    All .table(...).execute() calls will raise NotImplementedError.
    Migrate callers to fetch_one / fetch_all / execute.
    """
    print(
        "WARNING: get_supabase_client() called — this returns a migration shim. "
        "Migrate the caller to use fetch_one/fetch_all/execute directly."
    )
    return _shim


def get_user_client() -> _SupabaseShim:
    """
    Compatibility alias — returns a shim object.
    All .table(...).execute() calls will raise NotImplementedError.
    Migrate callers to fetch_one / fetch_all / execute.
    """
    print(
        "WARNING: get_user_client() called — this returns a migration shim. "
        "Migrate the caller to use fetch_one/fetch_all/execute directly."
    )
    return _shim
