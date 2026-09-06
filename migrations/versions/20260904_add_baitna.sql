-- Baitna — student housing lead generation.
-- Shared by the app backend (this repo) and the dashboard backend (separate repo,
-- same Supabase project). Additive only; the sole reference to an existing table
-- is a foreign key onto public.users(id).


-- 1. PARTNERS
CREATE TABLE IF NOT EXISTS baitna_partners (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name          text NOT NULL,
  property_name text,

  -- Embedded in lead_reference: 'AZIZ' -> BAITNA-AZIZ-260819-0042
  partner_code  text NOT NULL UNIQUE CHECK (partner_code ~ '^[A-Z0-9]{2,8}$'),

  logo_url      text,

  -- Where the "new lead" notice goes. Separate from baitna_partner_users.email,
  -- which is a dashboard login and may not exist when the first lead arrives.
  notification_emails text[] NOT NULL DEFAULT '{}',

  price_disclosure_enabled boolean NOT NULL DEFAULT true,
  is_signed     boolean NOT NULL DEFAULT false,
  is_active     boolean NOT NULL DEFAULT false,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_baitna_partners_active ON baitna_partners (is_active);


-- 2. LISTINGS
CREATE TABLE IF NOT EXISTS baitna_listings (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id   uuid NOT NULL REFERENCES baitna_partners(id) ON DELETE CASCADE,

  unit_type    text NOT NULL
               CHECK (unit_type IN ('en_suite','studio','shared_twin','one_bed','two_bed')),

  price_amount   numeric(10,2) CHECK (price_amount >= 0),
  price_currency text NOT NULL DEFAULT 'AED',

  availability_status text NOT NULL DEFAULT 'available'
               CHECK (availability_status IN ('available','limited','waitlist','unavailable')),

  image_urls   text[] NOT NULL DEFAULT '{}',

  -- Filter attributes, nullable so a partner can go live before every
  -- measurement is known.
  bedrooms          integer CHECK (bedrooms >= 0),
  bathrooms         integer CHECK (bathrooms >= 0),
  living_rooms      integer CHECK (living_rooms >= 0),
  area_sqft         numeric(10,2) CHECK (area_sqft > 0),
  occupancy_max     integer CHECK (occupancy_max > 0),

  -- Admin-maintained; no partner-facing write path exists.
  occupants_current integer CHECK (occupants_current >= 0),

  -- Generated because PostgREST cannot compare two columns in a filter.
  spots_available integer GENERATED ALWAYS AS (occupancy_max - occupants_current) STORED,

  -- price_amount when the partner discloses, NULL when they don't. The browse
  -- feed filters and sorts on this, so a hidden price can't be caught in a range
  -- or inferred from where the row lands. Trigger-maintained.
  price_sort   numeric(10,2),

  -- Popularity sort key. Trigger-maintained.
  lead_count   integer NOT NULL DEFAULT 0 CHECK (lead_count >= 0),

  is_active    boolean NOT NULL DEFAULT true,
  created_at   timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT baitna_listings_occupancy_sane CHECK (
    occupants_current IS NULL
    OR occupancy_max IS NULL
    OR occupants_current <= occupancy_max
  )
);

CREATE INDEX IF NOT EXISTS idx_baitna_listings_partner     ON baitna_listings (partner_id);
CREATE INDEX IF NOT EXISTS idx_baitna_listings_active_type ON baitna_listings (is_active, unit_type);
CREATE INDEX IF NOT EXISTS idx_baitna_listings_price       ON baitna_listings (price_sort);
CREATE INDEX IF NOT EXISTS idx_baitna_listings_spots       ON baitna_listings (spots_available);
CREATE INDEX IF NOT EXISTS idx_baitna_listings_lead_count  ON baitna_listings (lead_count DESC);
CREATE INDEX IF NOT EXISTS idx_baitna_listings_bedrooms    ON baitna_listings (bedrooms);
CREATE INDEX IF NOT EXISTS idx_baitna_listings_area        ON baitna_listings (area_sqft);
CREATE INDEX IF NOT EXISTS idx_baitna_listings_created     ON baitna_listings (created_at DESC);


-- 3. DASHBOARD ACCOUNTS
-- Here rather than in the dashboard repo because baitna_leads.acknowledged_by
-- references baitna_partner_users.
CREATE TABLE IF NOT EXISTS baitna_partner_users (
  id            uuid PRIMARY KEY,          -- same id as the Supabase Auth user
  partner_id    uuid NOT NULL UNIQUE REFERENCES baitna_partners(id) ON DELETE CASCADE,
  email         text NOT NULL UNIQUE,
  full_name     text,
  is_active     boolean NOT NULL DEFAULT true,
  last_login_at timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS baitna_admin_users (
  id            uuid PRIMARY KEY,          -- same id as the Supabase Auth user
  email         text NOT NULL UNIQUE,
  full_name     text,
  role          text NOT NULL DEFAULT 'admin' CHECK (role IN ('admin')),
  is_active     boolean NOT NULL DEFAULT true,
  last_login_at timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now()
);


-- 4. CONSENT EVENTS
CREATE TABLE IF NOT EXISTS consent_events (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id   uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,

  counterparty_name text NOT NULL,
  counterparty_ref  uuid REFERENCES baitna_partners(id),

  consent_version       text NOT NULL,
  consent_text_snapshot text NOT NULL,

  data_transfers_outside_uae boolean NOT NULL DEFAULT false,
  dpo_contact  text,
  ip_address   text,
  user_agent   text,

  accepted_at       timestamptz NOT NULL DEFAULT now(),
  withdrawn_at      timestamptz,
  withdrawal_reason text,

  -- No foreign key on purpose: baitna_leads.consent_event_id already points the
  -- other way, and a second FK here would make both tables uninsertable.
  related_record_type text,
  related_record_id   uuid
);

CREATE INDEX IF NOT EXISTS idx_consent_events_student ON consent_events (student_id);
CREATE INDEX IF NOT EXISTS idx_consent_events_related
  ON consent_events (related_record_type, related_record_id);


-- 5. LEADS
CREATE TABLE IF NOT EXISTS baitna_leads (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_reference text NOT NULL UNIQUE,

  student_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  partner_id     uuid NOT NULL REFERENCES baitna_partners(id),
  listing_id     uuid NOT NULL REFERENCES baitna_listings(id),

  move_in_date        date NOT NULL,
  lease_length_months integer NOT NULL CHECK (lease_length_months BETWEEN 1 AND 60),

  budget_band    text NOT NULL CHECK (budget_band IN
                 ('under_2000','2000_3500','3500_5000','5000_8000','above_8000')),
  current_status text NOT NULL CHECK (current_status IN
                 ('in_university_housing','in_private_housing','arriving_soon','looking_to_move')),

  -- Every lead has its own consent row, reroutes included.
  consent_event_id uuid NOT NULL REFERENCES consent_events(id),

  status         text NOT NULL DEFAULT 'submitted' CHECK (status IN (
                   'submitted','posted_to_dashboard','acknowledged','aging',
                   'converted','routed','withdrawn','closed_no_match','expired_stale'
                 )),

  submitted_at     timestamptz NOT NULL DEFAULT now(),
  posted_at        timestamptz,
  acknowledged_at  timestamptz,
  aging_flagged_at timestamptz,
  closed_at        timestamptz,

  acknowledged_by  uuid REFERENCES baitna_partner_users(id),

  commission_amount   numeric(12,2) CHECK (commission_amount >= 0),
  commission_currency text DEFAULT 'AED',
  commission_notes    text,

  routed_from_lead_id uuid REFERENCES baitna_leads(id),

  notification_sent    boolean NOT NULL DEFAULT false,
  notification_sent_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_baitna_leads_student ON baitna_leads (student_id, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_baitna_leads_partner ON baitna_leads (partner_id, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_baitna_leads_status  ON baitna_leads (status);
CREATE INDEX IF NOT EXISTS idx_baitna_leads_listing ON baitna_leads (listing_id);

-- One open inquiry per student per partner. The status list here, the BT001
-- check in baitna_create_lead, and constants.OPEN_STATUSES are the same set;
-- test_open_statuses_match_the_sql fails if they drift.
--
-- 'acknowledged' is included: a partner that has replied is still handling a live
-- inquiry, and leaving it out let a student open a second lead with that same
-- partner. Re-applying on a database created before this fix will fail if such a
-- pair already exists — find them first with:
--
--   SELECT student_id, partner_id, count(*), array_agg(lead_reference)
--   FROM baitna_leads
--   WHERE status IN ('submitted','posted_to_dashboard','acknowledged','aging')
--   GROUP BY student_id, partner_id HAVING count(*) > 1;
--
-- and close the duplicates (status 'closed_no_match') before continuing.
DROP INDEX IF EXISTS baitna_leads_one_open_per_student_partner;
CREATE UNIQUE INDEX baitna_leads_one_open_per_student_partner
  ON baitna_leads (student_id, partner_id)
  WHERE status IN ('submitted','posted_to_dashboard','acknowledged','aging');


-- 6. LEAD REFERENCE SEQUENCE
-- ON CONFLICT DO UPDATE ... RETURNING is atomic, so concurrent submissions can't
-- draw the same number. Day boundary is Asia/Dubai, matching the local calendar.
CREATE TABLE IF NOT EXISTS baitna_lead_sequences (
  partner_id uuid NOT NULL REFERENCES baitna_partners(id) ON DELETE CASCADE,
  seq_date   date NOT NULL,
  last_seq   integer NOT NULL DEFAULT 0,
  PRIMARY KEY (partner_id, seq_date)
);


-- 7. TRIGGERS

-- Stamp closed_at on every terminal transition; the 30-day floor measures from it.
CREATE OR REPLACE FUNCTION baitna_leads_set_closed_at()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status
     AND NEW.status IN ('converted','routed','withdrawn','closed_no_match','expired_stale')
     AND NEW.closed_at IS NULL
  THEN
    NEW.closed_at := now();
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_baitna_leads_set_closed_at ON baitna_leads;
CREATE TRIGGER trg_baitna_leads_set_closed_at
BEFORE UPDATE ON baitna_leads
FOR EACH ROW EXECUTE FUNCTION baitna_leads_set_closed_at();


-- 30-day floor. MESSAGE is student-facing; DETAIL is the bare ISO date so the
-- backend doesn't have to parse it out of prose.
CREATE OR REPLACE FUNCTION baitna_leads_enforce_floor()
RETURNS TRIGGER AS $$
DECLARE
  v_last_closed timestamptz;
  v_eligible    date;
BEGIN
  SELECT max(closed_at) INTO v_last_closed
  FROM baitna_leads
  WHERE student_id = NEW.student_id
    AND partner_id = NEW.partner_id
    AND closed_at IS NOT NULL;

  IF v_last_closed IS NOT NULL AND v_last_closed > now() - interval '30 days' THEN
    v_eligible := (v_last_closed + interval '30 days')::date;
    RAISE EXCEPTION
      'You submitted an inquiry to this partner recently. You can submit again after %.', v_eligible
      USING ERRCODE = 'BT002', DETAIL = v_eligible::text;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_baitna_leads_enforce_floor ON baitna_leads;
CREATE TRIGGER trg_baitna_leads_enforce_floor
BEFORE INSERT ON baitna_leads
FOR EACH ROW EXECUTE FUNCTION baitna_leads_enforce_floor();


-- Popularity counter. Never decremented: a withdrawn lead was still interest
-- expressed, and decrementing would make browse ordering jitter.
CREATE OR REPLACE FUNCTION baitna_bump_lead_count()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE baitna_listings
  SET lead_count = lead_count + 1
  WHERE id = NEW.listing_id;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_baitna_bump_lead_count ON baitna_leads;
CREATE TRIGGER trg_baitna_bump_lead_count
AFTER INSERT ON baitna_leads
FOR EACH ROW EXECUTE FUNCTION baitna_bump_lead_count();


-- price_sort needs two triggers because it depends on a column in another table.
CREATE OR REPLACE FUNCTION baitna_listings_set_price_sort()
RETURNS TRIGGER AS $$
DECLARE
  v_disclosed boolean;
BEGIN
  SELECT price_disclosure_enabled INTO v_disclosed
  FROM baitna_partners WHERE id = NEW.partner_id;

  NEW.price_sort := CASE WHEN coalesce(v_disclosed, false) THEN NEW.price_amount ELSE NULL END;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_baitna_listings_price_sort ON baitna_listings;
CREATE TRIGGER trg_baitna_listings_price_sort
BEFORE INSERT OR UPDATE OF price_amount, partner_id ON baitna_listings
FOR EACH ROW EXECUTE FUNCTION baitna_listings_set_price_sort();


CREATE OR REPLACE FUNCTION baitna_partners_refresh_price_sort()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE baitna_listings
  SET price_sort = CASE WHEN NEW.price_disclosure_enabled THEN price_amount ELSE NULL END
  WHERE partner_id = NEW.id;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_baitna_partners_price_sort ON baitna_partners;
CREATE TRIGGER trg_baitna_partners_price_sort
AFTER UPDATE OF price_disclosure_enabled ON baitna_partners
FOR EACH ROW
WHEN (OLD.price_disclosure_enabled IS DISTINCT FROM NEW.price_disclosure_enabled)
EXECUTE FUNCTION baitna_partners_refresh_price_sort();


-- 8. baitna_create_lead
-- supabase-py can't run a multi-statement transaction, so consent + reference +
-- lead are created here instead. Used by submission and by fallback rerouting.
--   BT001  open inquiry already exists for this (student, partner)
--   BT002  30-day floor in effect (raised by the trigger above)
--   BT003  partner or listing missing / inactive
--   BT004  student id null or absent from public.users
CREATE OR REPLACE FUNCTION baitna_create_lead(
  p_student_id                 uuid,
  p_partner_id                 uuid,
  p_listing_id                 uuid,
  p_move_in_date               date,
  p_lease_length_months        integer,
  p_budget_band                text,
  p_current_status             text,
  p_consent_version            text,
  p_consent_text_snapshot      text,
  p_data_transfers_outside_uae boolean DEFAULT false,
  p_dpo_contact                text DEFAULT NULL,
  p_ip_address                 text DEFAULT NULL,
  p_user_agent                 text DEFAULT NULL,
  p_routed_from_lead_id        uuid DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_partner    baitna_partners%ROWTYPE;
  v_listing    baitna_listings%ROWTYPE;
  v_consent_id uuid;
  v_seq        integer;
  v_today      date;
  v_reference  text;
  v_lead       baitna_leads%ROWTYPE;
BEGIN
  -- Without this a bad id surfaces as a NOT NULL violation from inside the
  -- consent insert.
  IF p_student_id IS NULL
     OR NOT EXISTS (SELECT 1 FROM users WHERE id = p_student_id)
  THEN
    RAISE EXCEPTION 'Student not found.' USING ERRCODE = 'BT004';
  END IF;

  SELECT * INTO v_partner
  FROM baitna_partners
  WHERE id = p_partner_id AND is_active = true;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Partner or listing not found or not currently active.'
      USING ERRCODE = 'BT003';
  END IF;

  SELECT * INTO v_listing
  FROM baitna_listings
  WHERE id = p_listing_id AND partner_id = p_partner_id AND is_active = true;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Partner or listing not found or not currently active.'
      USING ERRCODE = 'BT003';
  END IF;

  -- The partial unique index is the real guarantee; this is here for the message.
  -- Status list must match that index and constants.OPEN_STATUSES.
  IF EXISTS (
    SELECT 1 FROM baitna_leads
    WHERE student_id = p_student_id
      AND partner_id = p_partner_id
      AND status IN ('submitted','posted_to_dashboard','acknowledged','aging')
  ) THEN
    RAISE EXCEPTION
      'You already have an open inquiry with this partner. Please wait for a response or withdraw it first.'
      USING ERRCODE = 'BT001';
  END IF;

  -- Names the partner that actually receives the data, so a reroute never
  -- inherits consent given for someone else.
  INSERT INTO consent_events (
    student_id, counterparty_name, counterparty_ref,
    consent_version, consent_text_snapshot,
    data_transfers_outside_uae, dpo_contact, ip_address, user_agent,
    related_record_type
  ) VALUES (
    p_student_id, v_partner.name, v_partner.id,
    p_consent_version, p_consent_text_snapshot,
    coalesce(p_data_transfers_outside_uae, false), p_dpo_contact, p_ip_address, p_user_agent,
    'baitna_lead'
  )
  RETURNING id INTO v_consent_id;

  v_today := (now() AT TIME ZONE 'Asia/Dubai')::date;

  INSERT INTO baitna_lead_sequences (partner_id, seq_date, last_seq)
  VALUES (p_partner_id, v_today, 1)
  ON CONFLICT (partner_id, seq_date)
  DO UPDATE SET last_seq = baitna_lead_sequences.last_seq + 1
  RETURNING last_seq INTO v_seq;

  v_reference := 'BAITNA-' || v_partner.partner_code || '-'
                 || to_char(v_today, 'YYMMDD') || '-'
                 || lpad(v_seq::text, 4, '0');

  -- Straight to posted_to_dashboard; there is no separate posting step.
  INSERT INTO baitna_leads (
    lead_reference, student_id, partner_id, listing_id,
    move_in_date, lease_length_months, budget_band, current_status,
    consent_event_id, status, submitted_at, posted_at, routed_from_lead_id
  ) VALUES (
    v_reference, p_student_id, p_partner_id, p_listing_id,
    p_move_in_date, p_lease_length_months, p_budget_band, p_current_status,
    v_consent_id, 'posted_to_dashboard', now(), now(), p_routed_from_lead_id
  )
  RETURNING * INTO v_lead;

  UPDATE consent_events
  SET related_record_id = v_lead.id
  WHERE id = v_consent_id;

  RETURN jsonb_build_object(
    'id',                v_lead.id,
    'lead_reference',    v_lead.lead_reference,
    'status',            v_lead.status,
    'partner_id',        v_partner.id,
    'partner_name',      v_partner.name,
    'property_name',     v_partner.property_name,
    'listing_id',        v_listing.id,
    'unit_type',         v_listing.unit_type,
    'consent_event_id',  v_consent_id,
    'move_in_date',      v_lead.move_in_date,
    'submitted_at',      v_lead.submitted_at,
    'notification_emails', to_jsonb(v_partner.notification_emails)
  );
END;
$$;

-- Service role only; nothing anonymous should be able to mint a lead.
REVOKE ALL ON FUNCTION baitna_create_lead(
  uuid, uuid, uuid, date, integer, text, text, text, text, boolean, text, text, text, uuid
) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION baitna_create_lead(
  uuid, uuid, uuid, date, integer, text, text, text, text, boolean, text, text, text, uuid
) TO service_role;


-- 9. baitna_partner_lead_rows
-- Read by the dashboard backend. A withdrawn lead keeps its row as an audit
-- trail, but the contact details are blanked — consent to share them is revoked.
CREATE OR REPLACE VIEW baitna_partner_lead_rows AS
SELECT
  l.id,
  l.lead_reference,
  l.partner_id,
  l.listing_id,
  li.unit_type,

  -- public.users has no full_name: the display column is `name`, kept in step
  -- with first_name + last_name by the auth service. Older rows may carry only
  -- one of the two, so fall back rather than hand the partner a blank name.
  CASE WHEN l.status = 'withdrawn' THEN NULL ELSE coalesce(
         nullif(btrim(u.name), ''),
         nullif(btrim(concat_ws(' ', u.first_name, u.last_name)), '')
       ) END AS student_name,
  CASE WHEN l.status = 'withdrawn' THEN NULL ELSE u.email        END AS student_email,
  CASE WHEN l.status = 'withdrawn' THEN NULL ELSE u.phone_number END AS student_phone,

  l.move_in_date,
  l.lease_length_months,
  l.budget_band,
  l.current_status,
  l.status,
  (l.status = 'aging') AS is_aging,
  l.submitted_at,
  l.acknowledged_at,
  l.aging_flagged_at,
  l.closed_at
FROM baitna_leads l
JOIN users u            ON u.id  = l.student_id
JOIN baitna_listings li ON li.id = l.listing_id;

-- Views do NOT inherit the RLS of the tables they read. A view runs with its
-- owner's rights unless security_invoker is set, and the owner here also owns the
-- base tables, so it bypasses their RLS entirely. Supabase additionally grants
-- SELECT on new objects in `public` to anon and authenticated by default. Without
-- the two statements below, anyone holding the anon key — which ships inside the
-- mobile app — could read every student's name, email and phone through
-- /rest/v1/baitna_partner_lead_rows. The REVOKE is the guarantee and works on
-- every version; security_invoker is defence in depth and needs PG15+.
DO $do$
BEGIN
  IF current_setting('server_version_num')::int >= 150000 THEN
    EXECUTE 'ALTER VIEW baitna_partner_lead_rows SET (security_invoker = on)';
  END IF;
END
$do$;

REVOKE ALL ON baitna_partner_lead_rows FROM PUBLIC, anon, authenticated;
GRANT SELECT ON baitna_partner_lead_rows TO service_role;


-- 10. ROW LEVEL SECURITY
-- Enabled with no policies, so a leaked anon key reads no rows from these tables:
-- both backends hold the service key, which bypasses RLS. Note that this covers
-- tables only — the view above needed its own REVOKE, because RLS does not reach
-- through a view. Anything added here later needs the same treatment.
ALTER TABLE baitna_partners       ENABLE ROW LEVEL SECURITY;
ALTER TABLE baitna_listings       ENABLE ROW LEVEL SECURITY;
ALTER TABLE baitna_partner_users  ENABLE ROW LEVEL SECURITY;
ALTER TABLE baitna_admin_users    ENABLE ROW LEVEL SECURITY;
ALTER TABLE consent_events        ENABLE ROW LEVEL SECURITY;
ALTER TABLE baitna_leads          ENABLE ROW LEVEL SECURITY;
ALTER TABLE baitna_lead_sequences ENABLE ROW LEVEL SECURITY;


-- 11. SEED — uncomment on a staging project to smoke test.
-- INSERT INTO baitna_partners (name, property_name, partner_code, notification_emails,
--                              price_disclosure_enabled, is_signed, is_active)
-- VALUES ('Sample Residences', 'Sample Campus', 'SMPL', ARRAY['ops@example.com'],
--         true, true, false);
--
-- INSERT INTO baitna_listings (partner_id, unit_type, price_amount, availability_status,
--                              bedrooms, bathrooms, living_rooms, area_sqft,
--                              occupancy_max, occupants_current)
-- SELECT id, 'studio', 3500, 'available', 1, 1, 0, 480, 1, 0
-- FROM baitna_partners WHERE partner_code = 'SMPL';


-- 12. POST-APPLY CHECKS
-- Run on staging after applying. Set the email once, then work down the list.
-- Never paste a raw '<uuid>' placeholder — that gives 22P02, not a result.
--
-- CREATE TABLE IF NOT EXISTS baitna_test_ctx (email text);
-- DELETE FROM baitna_test_ctx;
-- INSERT INTO baitna_test_ctx VALUES ('student@example.edu');
-- SELECT u.id FROM users u, baitna_test_ctx c WHERE u.email = c.email;  -- must not be empty
--
-- (a) SELECT baitna_create_lead(
--       (SELECT u.id FROM users u, baitna_test_ctx c WHERE u.email = c.email),
--       (SELECT id FROM baitna_partners WHERE partner_code = 'SMPL'),
--       (SELECT l.id FROM baitna_listings l JOIN baitna_partners p ON p.id = l.partner_id
--         WHERE p.partner_code = 'SMPL' LIMIT 1),
--       '2026-10-01', 12, '3500_5000', 'arriving_soon',
--       'baitna_v1', 'consent text as shown to the student', false, 'privacy@example.com');
--     -> BAITNA-SMPL-<YYMMDD>-0001
-- (b) re-run (a)                        -> BT001
-- (c) UPDATE baitna_leads SET status='withdrawn';  then check closed_at is set
-- (d) re-run (a)                        -> BT002, DETAIL = eligible date
-- (e) re-run (a) with NULL student      -> BT004
-- (f) SELECT * FROM baitna_partner_lead_rows;      contact columns NULL
-- (g) SELECT lead_count FROM baitna_listings;      still 1 after the withdrawal
-- (h) toggle price_disclosure_enabled;             price_sort follows it
-- (i) set occupancy_max/occupants_current;         spots_available is the difference
--
-- DELETE FROM baitna_leads; DELETE FROM consent_events;
-- DELETE FROM baitna_lead_sequences; DROP TABLE IF EXISTS baitna_test_ctx;
