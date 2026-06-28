-- Personal email + lockout toggle
--
-- Collect a personal email from every user so OTP mail bypasses university
-- inboxes (which reject Postmark). Existing rows stay NULL until the admin
-- flips app_status.require_personal_email on, which forces the mobile app
-- to lock those users behind the PersonalEmailRequiredScreen until they
-- add and verify a personal email.

ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS personal_email              text,
  ADD COLUMN IF NOT EXISTS personal_email_verified_at  timestamptz;

CREATE INDEX IF NOT EXISTS idx_users_personal_email
  ON public.users (personal_email)
  WHERE personal_email IS NOT NULL;

ALTER TABLE public.app_status
  ADD COLUMN IF NOT EXISTS require_personal_email bool NOT NULL DEFAULT false;
