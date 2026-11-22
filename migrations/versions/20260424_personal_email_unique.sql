-- Enforce one-account-per-personal-email at the DB level.
--
-- The earlier migration created a non-unique partial index. Application code
-- already checks uniqueness at send-OTP, but there is a TOCTOU race between
-- send and verify: two users could race past the app check and both land
-- on verify. A UNIQUE partial index closes that race authoritatively.
--
-- Partial (WHERE personal_email IS NOT NULL) so existing users with NULL
-- personal_email don't collide.

DROP INDEX IF EXISTS idx_users_personal_email;

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_personal_email_unique
  ON public.users (personal_email)
  WHERE personal_email IS NOT NULL;
