"""
Database Module

Manages connection to Supabase.

IMPORTANT: The admin client (get_supabase_client) must NEVER have user sessions
injected into it via sign_in_with_password or set_session — this contaminates the
shared singleton and causes PGRST303 "JWT expired" errors on subsequent requests.

For any operation that calls supabase.auth.sign_in_with_password() or
supabase.auth.set_session(), use create_fresh_supabase_client() to get an
isolated client that won't pollute the global admin client.
"""

import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_supabase_url: str = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
_supabase_service_key: str = (
    os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY") or ""
).strip()
_supabase_anon_key: str = os.getenv("SUPABASE_ANON_KEY", "").strip()

# ---------------------------------------------------------------------------
# Singleton admin client — used for table queries and admin auth operations.
# NEVER call sign_in_with_password / set_session on this client.
# ---------------------------------------------------------------------------
_admin_client: Client | None = None


def _build_admin_client() -> Client | None:
    if not _supabase_url or not _supabase_service_key:
        print("WARNING: SUPABASE_URL or SUPABASE_SERVICE_KEY not found in environment")
        return None
    if _supabase_service_key.startswith("sb_publishable_"):
        print(
            "ERROR: SUPABASE_SERVICE_KEY requires a secret or service-role key, "
            "not a publishable key"
        )
        return None
    try:
        client = create_client(_supabase_url, _supabase_service_key)
        print("INFO: Initialized Supabase admin client")
        return client
    except Exception as e:
        print(
            f"ERROR: Failed to initialize Supabase client ({type(e).__name__}); "
            "check SUPABASE_URL and SUPABASE_SERVICE_KEY"
        )
        return None


_admin_client = _build_admin_client()


def get_supabase_client() -> Client | None:
    """
    Return the shared admin Supabase client.

    Use this for:
    - Table queries (supabase.table(...))
    - supabase.auth.admin.* operations
    - supabase.auth.get_user(token)

    Do NOT call sign_in_with_password / set_session on this client.
    """
    return _admin_client


def create_fresh_supabase_client() -> Client | None:
    """
    Create and return a brand-new Supabase client instance.

    Use this whenever you need to call:
    - supabase.auth.sign_in_with_password(...)
    - supabase.auth.sign_up(...)
    - supabase.auth.set_session(...)
    - supabase.auth.update_user(...)

    A fresh client keeps user session state isolated so the shared admin
    client is never contaminated.
    """
    if not _supabase_url or not _supabase_anon_key:
        print("WARNING: SUPABASE_URL or SUPABASE_ANON_KEY not found")
        return None
    if _supabase_anon_key.startswith("sb_secret_"):
        print("ERROR: SUPABASE_ANON_KEY requires an anon or publishable key, not a secret key")
        return None
    try:
        return create_client(_supabase_url, _supabase_anon_key)
    except Exception as e:
        print(
            f"ERROR: Failed to create fresh Supabase client ({type(e).__name__}); "
            "check SUPABASE_ANON_KEY"
        )
        return None


# Anon client
def get_user_client() -> Client | None:
    """
    Return a client using the ANON key for user-facing queries.
    Use this for queries that should respect RLS policies.
    """
    return create_fresh_supabase_client()


def validate_database_configuration() -> None:
    if _admin_client is None:
        raise RuntimeError(
            "Supabase admin client unavailable. Check SUPABASE_URL and SUPABASE_SERVICE_KEY."
        )
    public_client = get_user_client()
    if public_client is None:
        raise RuntimeError(
            "Supabase public client unavailable. Set SUPABASE_ANON_KEY "
            "to the matching project's anon or publishable key."
        )
    try:
        for client in (_admin_client, public_client):
            client.table("categories").select("id").limit(1).execute()
    except Exception as e:
        raise RuntimeError(
            f"Supabase database readiness check failed ({type(e).__name__}). "
            "Verify matching project URL/API keys and database migrations."
        ) from None
