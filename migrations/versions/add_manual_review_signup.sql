-- Migration: add manual review signup workflow
-- Purpose: support manual student verification with uploaded documents and admin review

ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS verification_status text,
  ADD COLUMN IF NOT EXISTS verification_submitted_at timestamptz,
  ADD COLUMN IF NOT EXISTS verification_reviewed_at timestamptz,
  ADD COLUMN IF NOT EXISTS verification_reviewed_by text,
  ADD COLUMN IF NOT EXISTS verification_rejection_reason text,
  ADD COLUMN IF NOT EXISTS signup_method text;

UPDATE public.users
SET
  verification_status = COALESCE(verification_status, 'approved'),
  signup_method = COALESCE(signup_method, 'legacy_otp')
WHERE verification_status IS NULL
   OR signup_method IS NULL;

ALTER TABLE public.users
  ALTER COLUMN verification_status SET DEFAULT 'approved';

ALTER TABLE public.users
  ADD CONSTRAINT users_verification_status_check
    CHECK (verification_status IN ('pending_review', 'approved', 'rejected'));

ALTER TABLE public.users
  ADD CONSTRAINT users_signup_method_check
    CHECK (signup_method IN ('manual_review', 'azure_oauth', 'legacy_otp'));

CREATE INDEX IF NOT EXISTS idx_users_verification_status
  ON public.users (verification_status);

CREATE TABLE IF NOT EXISTS public.user_verification_submissions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'pending_review'
    CHECK (status IN ('pending_review', 'approved', 'rejected', 'superseded')),
  enrollment_document_path text,
  enrollment_document_name text,
  student_id_document_path text,
  student_id_document_name text,
  rejection_reason text,
  reviewed_by text,
  reviewed_at timestamptz,
  submitted_at timestamptz NOT NULL DEFAULT timezone('utc'::text, now()),
  created_at timestamptz NOT NULL DEFAULT timezone('utc'::text, now())
);

-- Backfill for databases where the table already existed before this migration
-- (CREATE TABLE IF NOT EXISTS is a no-op on pre-existing tables, so column
-- additions must be applied separately).
ALTER TABLE public.user_verification_submissions
  ADD COLUMN IF NOT EXISTS enrollment_document_path text,
  ADD COLUMN IF NOT EXISTS enrollment_document_name text,
  ADD COLUMN IF NOT EXISTS student_id_document_path text,
  ADD COLUMN IF NOT EXISTS student_id_document_name text,
  ADD COLUMN IF NOT EXISTS rejection_reason text,
  ADD COLUMN IF NOT EXISTS reviewed_by text,
  ADD COLUMN IF NOT EXISTS reviewed_at timestamptz,
  ADD COLUMN IF NOT EXISTS submitted_at timestamptz NOT NULL DEFAULT timezone('utc'::text, now());

NOTIFY pgrst, 'reload schema';

CREATE INDEX IF NOT EXISTS idx_user_verification_submissions_user_id
  ON public.user_verification_submissions (user_id);

CREATE INDEX IF NOT EXISTS idx_user_verification_submissions_status
  ON public.user_verification_submissions (status);

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'user-verification-documents',
  'user-verification-documents',
  false,
  10485760,
  ARRAY['application/pdf', 'image/jpeg', 'image/png']
)
ON CONFLICT (id) DO UPDATE
SET
  public = EXCLUDED.public,
  file_size_limit = EXCLUDED.file_size_limit,
  allowed_mime_types = EXCLUDED.allowed_mime_types;
