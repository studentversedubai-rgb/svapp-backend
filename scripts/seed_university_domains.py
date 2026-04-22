"""
Seed University Domains

Idempotent script to populate the university_domains table from seed data.
Uses upsert (INSERT ... ON CONFLICT DO UPDATE) so it is safe to re-run.

Usage:
    python scripts/seed_university_domains.py

Requires SUPABASE_URL and SUPABASE_SERVICE_KEY in environment (or .env file).
"""

import json
import os
import sys

# Add the project root to sys.path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY") or ""

SEED_FILE = os.path.join(os.path.dirname(__file__), "university_domains_seed.json")


def main():
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.")
        sys.exit(1)

    # Import here so env vars are loaded first
    from supabase import create_client

    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    # Load seed data
    with open(SEED_FILE, "r", encoding="utf-8") as f:
        seed_data = json.load(f)

    if not seed_data:
        print("WARNING: Seed file is empty. Nothing to do.")
        return

    print(f"Loaded {len(seed_data)} entries from seed file.")

    inserted = 0
    updated = 0
    errors = 0

    for entry in seed_data:
        university_name = entry.get("university_name", "").strip()
        domain = entry.get("domain", "").strip().lower()

        if not university_name or not domain:
            print(f"  SKIP: Missing university_name or domain in entry: {entry}")
            errors += 1
            continue

        try:
            # Check if domain already exists
            existing = (
                supabase.table("university_domains")
                .select("id, university_name")
                .eq("domain", domain)
                .execute()
            )

            if existing.data:
                # Update university_name if it changed
                row = existing.data[0]
                if row["university_name"] != university_name:
                    supabase.table("university_domains").update(
                        {"university_name": university_name, "is_active": True}
                    ).eq("id", row["id"]).execute()
                    print(f"  UPDATED: {domain} → {university_name}")
                    updated += 1
                else:
                    print(f"  EXISTS:  {domain} ({university_name})")
            else:
                # Insert new row
                supabase.table("university_domains").insert(
                    {
                        "university_name": university_name,
                        "domain": domain,
                        "is_active": True,
                    }
                ).execute()
                print(f"  INSERT:  {domain} → {university_name}")
                inserted += 1

        except Exception as e:
            print(f"  ERROR:   {domain} — {e}")
            errors += 1

    print(f"\nDone. Inserted: {inserted}, Updated: {updated}, Errors: {errors}")


if __name__ == "__main__":
    main()
