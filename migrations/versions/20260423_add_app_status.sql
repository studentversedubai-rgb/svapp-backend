-- App-wide status / maintenance / force-update / custom alert
-- Single-row config table consumed by the mobile app (polled + realtime subscribed)
-- and written by sv-dashboard (service-role).

CREATE TABLE IF NOT EXISTS app_status (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  singleton     bool NOT NULL DEFAULT true UNIQUE CHECK (singleton = true),

  mode          text NOT NULL DEFAULT 'normal'
                CHECK (mode IN ('normal','maintenance','emergency','force_update','custom')),

  -- Force-update fields
  min_ios_version          text,
  min_android_version      text,
  update_dismissible       bool NOT NULL DEFAULT true,
  update_store_url_ios     text,
  update_store_url_android text,

  -- Custom alert fields (used when mode = 'custom')
  alert_title        text,
  alert_body         text,
  alert_icon         text,
  alert_accent_color text,
  alert_cta_label    text,
  alert_cta_url      text,
  alert_dismissible  bool NOT NULL DEFAULT false,

  updated_at  timestamptz NOT NULL DEFAULT now(),
  updated_by  text
);

-- Seed the single row
INSERT INTO app_status (singleton, mode)
VALUES (true, 'normal')
ON CONFLICT (singleton) DO NOTHING;

-- Auto-bump updated_at on every write
CREATE OR REPLACE FUNCTION app_status_touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_app_status_updated_at ON app_status;
CREATE TRIGGER trg_app_status_updated_at
BEFORE UPDATE ON app_status
FOR EACH ROW EXECUTE FUNCTION app_status_touch_updated_at();

-- Publish to Supabase Realtime so the mobile app gets instant updates
ALTER PUBLICATION supabase_realtime ADD TABLE app_status;

-- RLS: public read, no public write (writes use the service-role key from sv-dashboard)
ALTER TABLE app_status ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS app_status_public_read ON app_status;
CREATE POLICY app_status_public_read
  ON app_status FOR SELECT
  USING (true);
