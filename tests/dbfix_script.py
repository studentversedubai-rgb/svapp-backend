#!/usr/bin/env python3
"""
RLS Validation Script for StudentVerse
Tests all tables defined in access policy spec.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

USERS = {
    "user_a": {"email": "rls_test1@test.com", "password": "123t"},
    "user_b": {"email": "rls_test2@test.com", "password": "456t"},
}

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def header(title):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def section(title):
    print(f"\n  📁 {title}")

def get_token(email, password):
    try:
        r = requests.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
            json={"email": email, "password": password},
        )
        if r.status_code == 200:
            return r.json()["access_token"]
        print(f"    ⚠️  Could not get token for {email}: {r.status_code}")
    except Exception as e:
        print(f"    ⚠️  Token fetch error: {e}")
    return None

def get_client(token=None):
    try:
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        if token:
            client.postgrest.auth(token)
        return client
    except Exception as e:
        print(f"    ⚠️  Client creation error: {e}")
        return None

def get_user_id(token):
    try:
        import base64, json
        payload = token.split(".")[1]
        payload += "=" * (4 - len(payload) % 4)
        return json.loads(base64.b64decode(payload))["sub"]
    except Exception:
        return None

# ──────────────────────────────────────────────
# Primitive test helpers
# ──────────────────────────────────────────────

def check(label, actual_pass, should_pass):
    if actual_pass == should_pass:
        mark = "✅ PASS"
    else:
        mark = f"❌ FAIL ({'allowed but should block' if actual_pass else 'blocked but should allow'})"
    print(f"     {label}: {mark}")

def try_select(client, table, columns="*"):
    try:
        r = client.table(table).select(columns).limit(5).execute()
        return True, r.data
    except Exception as e:
        return False, str(e)

def try_insert(client, table, data):
    try:
        client.table(table).insert(data).execute()
        return True
    except Exception:
        return False

def try_update(client, table, match_col, match_val, data):
    """
    Returns True only if rows were actually modified.
    RLS silently returns 0 rows on blocked updates — treat that as blocked.
    """
    try:
        r = client.table(table).update(data).eq(match_col, match_val).execute()
        print(f"     [DEBUG] UPDATE {table} response: data={r.data}")
        return len(r.data) > 0
    except Exception as e:
        print(f"     [DEBUG] UPDATE {table} exception: {e}")
        return False

def try_delete(client, table, match_col, match_val):
    try:
        client.table(table).delete().eq(match_col, match_val).execute()
        return True
    except Exception:
        return False

def check_blocked(label, client, table):
    """
    For tables/roles where SELECT should return nothing.
    RLS returns HTTP 200 with empty array — NOT an exception.
    Pass = got 200 with 0 rows.
    Fail = got actual rows back.
    """
    ok, data = try_select(client, table)
    if not ok:
        print(f"     {label}: ✅ PASS (blocked with error)")
        return
    if len(data) == 0:
        print(f"     {label}: ✅ PASS (RLS blocked — empty result)")
    else:
        print(f"     {label}: ❌ FAIL (got {len(data)} rows — should be empty)")

# ──────────────────────────────────────────────
# Per-table tests
# ──────────────────────────────────────────────

def test_public_read_only_table(client, table, insert_data, label):
    section(f"{table}  —  {label}")
    ok, data = try_select(client, table)
    check("SELECT (everyone can read)", ok and data is not None, should_pass=True)
    ok = try_insert(client, table, insert_data)
    check("INSERT (blocked for users/anon)", ok, should_pass=False)


def test_users_table(client_self, user_id_self, client_other, user_id_other):
    section("test_users  —  Read/Write own row only")

    ok, data = try_select(client_self, "test_users")
    if ok:
        ids = [r.get("id") for r in (data or [])]
        own_only = all(i == user_id_self for i in ids) if ids else True
        check("SELECT returns only own row", own_only, should_pass=True)
    else:
        check("SELECT own row", False, should_pass=True)

    # UPDATE own row — debug will show exactly what comes back
    ok = try_update(client_self, "test_users", "id", user_id_self, {"full_name": "RLS Test Updated"})
    check("UPDATE own row (allowed)", ok, should_pass=True)

    ok = try_insert(client_self, "test_users", {"email": "rogue@test.com", "full_name": "Rogue"})
    check("INSERT new row (blocked)", ok, should_pass=False)

    if user_id_other:
        ok = try_update(client_self, "test_users", "id", user_id_other, {"full_name": "Hacked"})
        check("UPDATE another user's row (blocked)", ok, should_pass=False)


def test_redemptions_table(client_self, user_id_self, client_other, user_id_other):
    section("test_redemptions  —  Read own only, write backend only")

    ok, data = try_select(client_self, "test_redemptions")
    if ok:
        ids = [r.get("user_id") for r in (data or [])]
        own_only = all(i == user_id_self for i in ids) if ids else True
        check("SELECT returns only own redemptions", own_only, should_pass=True)
    else:
        check("SELECT own redemptions", False, should_pass=True)

    ok = try_insert(client_self, "test_redemptions", {
        "user_id": user_id_self, "offer_id": "00000000-0000-0000-0000-000000000000",
        "total_bill_amount": 100, "discount_amount": 10, "final_amount": 90, "offer_type": "discount"
    })
    check("INSERT redemption (blocked)", ok, should_pass=False)

    if client_other and user_id_other:
        ok, data = try_select(client_self, "test_redemptions")
        if ok:
            leaked = any(r.get("user_id") == user_id_other for r in (data or []))
            check("SELECT does NOT leak other user's redemptions", not leaked, should_pass=True)


def test_entitlements_table(client_self, user_id_self, client_other, user_id_other):
    section("test_entitlements  —  Read own only, write backend only")

    ok, data = try_select(client_self, "test_entitlements")
    if ok:
        ids = [r.get("user_id") for r in (data or [])]
        own_only = all(i == user_id_self for i in ids) if ids else True
        check("SELECT returns only own entitlements", own_only, should_pass=True)
    else:
        check("SELECT own entitlements", False, should_pass=True)

    ok = try_insert(client_self, "test_entitlements", {
        "user_id": user_id_self, "offer_id": "00000000-0000-0000-0000-000000000000"
    })
    check("INSERT entitlement (blocked)", ok, should_pass=False)

    if client_other and user_id_other:
        ok, data = try_select(client_self, "test_entitlements")
        if ok:
            leaked = any(r.get("user_id") == user_id_other for r in (data or []))
            check("SELECT does NOT leak other user's entitlements", not leaked, should_pass=True)


def test_ticket_records_table(client_self, user_id_self, client_other, user_id_other):
    section("test_ticket_records  —  Read own only, write backend only")

    ok, data = try_select(client_self, "test_ticket_records")
    if ok:
        ids = [r.get("user_id") for r in (data or [])]
        own_only = all(i == user_id_self for i in ids) if ids else True
        check("SELECT returns only own ticket records", own_only, should_pass=True)
    else:
        check("SELECT own ticket records", False, should_pass=True)

    ok = try_insert(client_self, "test_ticket_records", {
        "user_id": user_id_self, "ticket_id": "00000000-0000-0000-0000-000000000000"
    })
    check("INSERT ticket record (blocked)", ok, should_pass=False)

    if client_other and user_id_other:
        ok, data = try_select(client_self, "test_ticket_records")
        if ok:
            leaked = any(r.get("user_id") == user_id_other for r in (data or []))
            check("SELECT does NOT leak other user's ticket records", not leaked, should_pass=True)


def test_verification_submissions_table(client_self, user_id_self, client_other, user_id_other):
    section("test_user_verification_submissions  —  Own read + create, backend updates")

    ok, data = try_select(client_self, "test_user_verification_submissions")
    if ok:
        ids = [r.get("user_id") for r in (data or [])]
        own_only = all(i == user_id_self for i in ids) if ids else True
        check("SELECT returns only own submissions", own_only, should_pass=True)
    else:
        check("SELECT own submissions", False, should_pass=True)

    ok = try_insert(client_self, "test_user_verification_submissions", {
        "user_id": user_id_self, "status": "pending_review"
    })
    check("INSERT own submission (allowed)", ok, should_pass=True)

    ok, data = try_select(client_self, "test_user_verification_submissions")
    if ok and data:
        sub_id = data[0]["id"]
        ok = try_update(client_self, "test_user_verification_submissions", "id", sub_id, {"status": "approved"})
        check("UPDATE submission status (blocked — backend only)", ok, should_pass=False)

    if client_other and user_id_other:
        ok, data = try_select(client_self, "test_user_verification_submissions")
        if ok:
            leaked = any(r.get("user_id") == user_id_other for r in (data or []))
            check("SELECT does NOT leak other user's submissions", not leaked, should_pass=True)


def test_blacklist_table(client_self, user_id_self):
    section("test_user_blacklist  —  Own read only, write backend only")

    ok, data = try_select(client_self, "test_user_blacklist")
    if ok:
        ids = [r.get("user_id") or r.get("id") for r in (data or [])]
        leaking = any(i != user_id_self for i in ids if i)
        check("SELECT returns only own blacklist entry (if any)", not leaking, should_pass=True)
    else:
        check("SELECT blocked (ok if user is not blacklisted)", True, should_pass=True)

    ok = try_insert(client_self, "test_user_blacklist", {"email": "victim@test.com"})
    check("INSERT (blocked)", ok, should_pass=False)


def test_analytics_table(client_self, label=""):
    section(f"test_analytics_events  —  Backend only{' (' + label + ')' if label else ''}")
    check_blocked("SELECT returns no rows (RLS)", client_self, "test_analytics_events")
    ok = try_insert(client_self, "test_analytics_events", {"event_type": "test"})
    check("INSERT (blocked)", ok, should_pass=False)


def test_merchants_sensitive_columns(client_self):
    section("test_merchants  —  Sensitive column exposure check")
    ok, data = try_select(client_self, "test_merchants")
    if ok and data:
        exposed_pin_hash = any("pin_hash" in row for row in data)
        exposed_pin_exp  = any("pin_expires_at" in row for row in data)
        check("pin_hash NOT exposed in response", not exposed_pin_hash, should_pass=True)
        check("pin_expires_at NOT exposed in response", not exposed_pin_exp, should_pass=True)
    else:
        print("     ⚠️  No merchant rows found — column exposure check skipped")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main():
    header("STUDENTVERSE RLS VALIDATION")

    print("\n📋 Environment:")
    print(f"   SUPABASE_URL:      {'✅' if SUPABASE_URL else '❌ MISSING'}")
    print(f"   SUPABASE_ANON_KEY: {'✅' if SUPABASE_ANON_KEY else '❌ MISSING'}")
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        print("\n❌ Aborting — missing env vars.")
        return

    token_a = get_token(USERS["user_a"]["email"], USERS["user_a"]["password"])
    token_b = get_token(USERS["user_b"]["email"], USERS["user_b"]["password"])
    client_anon = get_client()
    client_a    = get_client(token_a) if token_a else None
    client_b    = get_client(token_b) if token_b else None
    uid_a = get_user_id(token_a) if token_a else None
    uid_b = get_user_id(token_b) if token_b else None

    print(f"\n   User A ID: {uid_a or '❌ not resolved'}")
    print(f"   User B ID: {uid_b or '❌ not resolved'}")

    # ── UNAUTHENTICATED ───────────────────────────────────────────────
    header("🔓 UNAUTHENTICATED (anon)")
    test_public_read_only_table(client_anon, "test_categories",        {"name": "RLS_X", "slug": "rls-x"},        "Public read-only")
    test_public_read_only_table(client_anon, "test_offers",            {"title": "RLS", "offer_type": "discount"}, "Public read-only")
    test_public_read_only_table(client_anon, "test_merchants",         {"name": "RLS Merchant"},                   "Public read-only")
    test_public_read_only_table(client_anon, "test_online_deals",      {"title": "RLS Deal"},                      "Public read-only")
    test_public_read_only_table(client_anon, "test_tickets",           {"title": "RLS Ticket"},                    "Public read-only")
    test_public_read_only_table(client_anon, "test_university_domains",{"domain": "rls.ac.ae"},                    "Public read-only")

    section("test_users  —  anon blocked entirely")
    check_blocked("SELECT returns no rows (RLS)", client_anon, "test_users")

    test_analytics_table(client_anon, "anon")

    section("test_user_blacklist  —  anon blocked")
    check_blocked("SELECT returns no rows (RLS)", client_anon, "test_user_blacklist")

    # ── USER A ────────────────────────────────────────────────────────
    header("👤 USER A")
    if client_a and uid_a:
        test_public_read_only_table(client_a, "test_categories",        {"name": "RLS_X2", "slug": "rls-x2"},       "Public read-only")
        test_public_read_only_table(client_a, "test_offers",            {"title": "RLS2", "offer_type": "discount"}, "Public read-only")
        test_public_read_only_table(client_a, "test_merchants",         {"name": "RLS Merchant 2"},                  "Public read-only")
        test_public_read_only_table(client_a, "test_online_deals",      {"title": "RLS Deal 2"},                     "Public read-only")
        test_public_read_only_table(client_a, "test_tickets",           {"title": "RLS Ticket 2"},                   "Public read-only")
        test_public_read_only_table(client_a, "test_university_domains",{"domain": "rls2.ac.ae"},                    "Public read-only")
        test_merchants_sensitive_columns(client_a)
        test_users_table(client_a, uid_a, client_b, uid_b)
        test_redemptions_table(client_a, uid_a, client_b, uid_b)
        test_entitlements_table(client_a, uid_a, client_b, uid_b)
        test_ticket_records_table(client_a, uid_a, client_b, uid_b)
        test_verification_submissions_table(client_a, uid_a, client_b, uid_b)
        test_blacklist_table(client_a, uid_a)
        test_analytics_table(client_a, "User A")
    else:
        print("  ❌ Skipping User A tests — auth failed")

    # ── USER B ────────────────────────────────────────────────────────
    header("👤 USER B")
    if client_b and uid_b:
        test_users_table(client_b, uid_b, client_a, uid_a)
        test_redemptions_table(client_b, uid_b, client_a, uid_a)
        test_entitlements_table(client_b, uid_b, client_a, uid_a)
        test_ticket_records_table(client_b, uid_b, client_a, uid_a)
        test_verification_submissions_table(client_b, uid_b, client_a, uid_a)
        test_blacklist_table(client_b, uid_b)
        test_analytics_table(client_b, "User B")
    else:
        print("  ❌ Skipping User B tests — auth failed")

    header("DONE")
    print("""
  ✅ PASS = Behaves as specified
  ❌ FAIL = Policy mismatch — fix required
  ⚠️  = Warning / manual check needed
    """)

if __name__ == "__main__":
    main()
