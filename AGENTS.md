# Backend verification

- Use Python 3.11, matching the Docker image. Local tests can run with `.venv/bin/python -m pytest tests/unit -q`.
- Unit-test runs should set dummy `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY`, and `POSTMARK_API_KEY` environment values; do not use live credentials or run database-mutating integration/E2E tests without explicit approval.
- Supabase Python 2.9.0 rejects modern publishable/secret keys locally. The pinned 2.16.0 release supports those keys while retaining compatibility with the existing Pydantic/FastAPI pins.
- Keep admin database clients isolated from user auth sessions. User-facing/RLS clients must use the anon/publishable key, never the secret key.
- Startup and `/health` perform read-only database readiness queries. Railway/production deployments require shared Redis; memory fallback is local-development only.
- OTP/review emails use `POSTMARK_API_KEY` and a verified `REVIEW_FROM_ADDRESS`. The older Resend placeholders do not configure Postmark.
