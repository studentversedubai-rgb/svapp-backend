ALTER TABLE public.users
  DROP CONSTRAINT IF EXISTS users_signup_method_check;

ALTER TABLE public.users
  ADD CONSTRAINT users_signup_method_check
  CHECK (signup_method IN ('manual_review', 'automated_ai', 'azure_oauth', 'legacy_otp'));
