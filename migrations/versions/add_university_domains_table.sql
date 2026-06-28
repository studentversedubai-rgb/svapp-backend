-- Migration: Add university_domains table
-- Purpose: Backend-owned whitelist of verified university email domains
--          Used by Microsoft OAuth sign-up and forgot-password flows
--          to validate that the user's email belongs to a supported institution.
--
-- This table replaces the frontend heuristic (.edu / .ac. pattern matching)
-- with exact domain matching against a verified list.
--
-- Safe to run on production: creates new table, does not modify existing tables.

CREATE TABLE IF NOT EXISTS public.university_domains (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  university_name text NOT NULL,
  domain text NOT NULL,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Ensure exact-match domain lookups are fast and unique
CREATE UNIQUE INDEX IF NOT EXISTS idx_university_domains_domain_lower
  ON public.university_domains (lower(domain));

-- Index for listing active universities
CREATE INDEX IF NOT EXISTS idx_university_domains_active
  ON public.university_domains (is_active) WHERE is_active = true;
