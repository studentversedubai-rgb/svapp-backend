-- Expand verification_status domain to include 'suspended'
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_verification_status_check;
ALTER TABLE users ADD CONSTRAINT users_verification_status_check
  CHECK (verification_status IN ('pending_review','approved','rejected','suspended'));

-- Running count kept on users for fast lookup (trigger maintains it)
ALTER TABLE users ADD COLUMN IF NOT EXISTS rejection_count INT NOT NULL DEFAULT 0;

-- Blacklist table — one row per suspended email. Keyed by email (not user_id)
-- so that a user recreating an account with the same email is still blocked.
CREATE TABLE IF NOT EXISTS user_blacklist (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text NOT NULL UNIQUE,
  user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  rejection_count int NOT NULL,
  reasons text[] NOT NULL DEFAULT '{}',
  blacklisted_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_user_blacklist_email_lower
  ON user_blacklist (LOWER(email));

-- Trigger: when a verification submission transitions to 'rejected',
-- increment users.rejection_count. If count >= 3, upsert into user_blacklist
-- and set users.verification_status = 'suspended'.
CREATE OR REPLACE FUNCTION handle_rejection_blacklist()
RETURNS TRIGGER AS $$
DECLARE
  v_count INT;
  v_email TEXT;
  v_reasons TEXT[];
BEGIN
  IF NEW.status = 'rejected'
     AND (TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM 'rejected') THEN

    SELECT COUNT(*) INTO v_count
    FROM user_verification_submissions
    WHERE user_id = NEW.user_id AND status = 'rejected';

    UPDATE users SET rejection_count = v_count WHERE id = NEW.user_id;

    IF v_count >= 3 THEN
      SELECT email INTO v_email FROM users WHERE id = NEW.user_id;

      SELECT COALESCE(array_agg(rejection_reason ORDER BY reviewed_at DESC)
                      FILTER (WHERE rejection_reason IS NOT NULL), '{}')
        INTO v_reasons
      FROM user_verification_submissions
      WHERE user_id = NEW.user_id AND status = 'rejected';

      INSERT INTO user_blacklist (email, user_id, rejection_count, reasons)
      VALUES (v_email, NEW.user_id, v_count, v_reasons)
      ON CONFLICT (email) DO UPDATE
        SET rejection_count = EXCLUDED.rejection_count,
            reasons = EXCLUDED.reasons,
            user_id = EXCLUDED.user_id;

      UPDATE users
        SET verification_status = 'suspended'
        WHERE id = NEW.user_id;
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_handle_rejection_blacklist ON user_verification_submissions;
CREATE TRIGGER trg_handle_rejection_blacklist
AFTER INSERT OR UPDATE OF status ON user_verification_submissions
FOR EACH ROW EXECUTE FUNCTION handle_rejection_blacklist();
