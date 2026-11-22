-- Migration: Add password_hash column to users table for self-managed auth
-- Run once after migrating from Supabase to Azure PostgreSQL

ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;

-- Index for faster email lookups during login
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
CREATE INDEX IF NOT EXISTS idx_users_personal_email ON users (personal_email);

-- Note: Existing users will have NULL password_hash.
-- They must reset their password on first login after migration.
-- The login endpoint handles NULL password_hash by returning a 401 with
-- a "password_reset_required" code so the frontend can redirect them.
