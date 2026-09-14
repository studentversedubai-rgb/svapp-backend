-- Baitna — unit switching and the distance-to-university line on partner tiles.
--
-- Additive to 20260904_add_baitna.sql: new columns with defaults, one new table,
-- one new function. Nothing existing is altered or dropped, so the dashboard
-- backend (separate repo, same Supabase project) is unaffected.


-- ============================================================================
-- 1. COORDINATES
-- ============================================================================
-- Both sides of the distance calculation. The backend computes a straight-line
-- (haversine) distance in Python and reports nothing at all when either side is
-- missing, so these can be filled in partner by partner without the tile ever
-- showing a wrong or half-built figure.

ALTER TABLE baitna_partners
  ADD COLUMN IF NOT EXISTS latitude  numeric(9,6),
  ADD COLUMN IF NOT EXISTS longitude numeric(9,6);

-- Named so a re-run does not stack duplicate constraints.
DO $do$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'baitna_partners_coords_valid'
  ) THEN
    ALTER TABLE baitna_partners ADD CONSTRAINT baitna_partners_coords_valid CHECK (
      (latitude IS NULL AND longitude IS NULL)
      OR (latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)
    );
  END IF;
END
$do$;

ALTER TABLE university_domains
  ADD COLUMN IF NOT EXISTS latitude  numeric(9,6),
  ADD COLUMN IF NOT EXISTS longitude numeric(9,6);

DO $do$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'university_domains_coords_valid'
  ) THEN
    ALTER TABLE university_domains ADD CONSTRAINT university_domains_coords_valid CHECK (
      (latitude IS NULL AND longitude IS NULL)
      OR (latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)
    );
  END IF;
END
$do$;


-- Campus coordinates for the domains scripts/university_domains_seed.json
-- already seeds. Approximate to the campus entrance, which is the right
-- precision for a "12 km away" line on a tile.
--
-- Only fills blanks: a coordinate corrected by hand in the dashboard is never
-- overwritten by a re-run of this migration.
UPDATE university_domains AS u
SET latitude = c.lat, longitude = c.lon
FROM (VALUES
  ('aue.ae',                  25.118000, 55.409800),  -- American University in the Emirates
  ('aud.edu',                 25.099500, 55.172800),  -- American University in Dubai
  ('aus.edu',                 25.309500, 55.491500),  -- American University of Sharjah
  ('buid.ac.ae',              25.124700, 55.405300),  -- British University in Dubai
  ('cud.ac.ae',               25.209800, 55.268300),  -- Canadian University Dubai
  ('student.curtin.edu.au',   25.118300, 55.408800),  -- Curtin University Dubai
  ('dmcg.edu',                25.280300, 55.382300),  -- Dubai Medical College
  ('hw.ac.uk',                25.100700, 55.162600),  -- Heriot-Watt University Dubai
  ('hult.edu',                25.123200, 55.407400),  -- Hult International Business School
  ('live.mdx.ac.uk',          25.101500, 55.163200),  -- Middlesex University Dubai
  ('student.murdoch.edu.au',  25.101100, 55.162000),  -- Murdoch University Dubai
  ('rit.edu',                 25.119500, 55.381000),  -- RIT Dubai
  ('spjain.org',              25.125800, 55.409500),  -- SP Jain School of Global Management
  ('uaeu.ac.ae',              24.202800, 55.677300),  -- UAE University, Al Ain
  ('bham.ac.uk',              25.121100, 55.414900),  -- University of Birmingham Dubai
  ('ud.ac.ae',                25.126800, 55.414500),  -- University of Dubai
  ('uowmail.edu.au',          25.100500, 55.161600),  -- University of Wollongong in Dubai
  ('zu.ac.ae',                25.126300, 55.418500)   -- Zayed University
) AS c(domain, lat, lon)
WHERE lower(u.domain) = c.domain
  AND u.latitude IS NULL
  AND u.longitude IS NULL;


-- ============================================================================
-- 2. LISTING SWITCH LOG
-- ============================================================================
-- One row per switch. The quota is counted from this table rather than from a
-- column on the lead, because the window is per (student, partner) and rolling:
-- a counter on the lead could not answer "how many in the last 30 days" once a
-- lead closes and another opens with the same partner.

CREATE TABLE IF NOT EXISTS baitna_lead_listing_switches (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id         uuid NOT NULL REFERENCES baitna_leads(id) ON DELETE CASCADE,
  student_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  partner_id      uuid NOT NULL REFERENCES baitna_partners(id) ON DELETE CASCADE,
  from_listing_id uuid NOT NULL REFERENCES baitna_listings(id),
  to_listing_id   uuid NOT NULL REFERENCES baitna_listings(id),
  switched_at     timestamptz NOT NULL DEFAULT now()
);

-- The quota read: newest first within one (student, partner).
CREATE INDEX IF NOT EXISTS idx_baitna_switches_quota
  ON baitna_lead_listing_switches (student_id, partner_id, switched_at DESC);

CREATE INDEX IF NOT EXISTS idx_baitna_switches_lead
  ON baitna_lead_listing_switches (lead_id);

-- Same posture as every other Baitna table: enabled with no policies, so a
-- leaked anon key reads nothing. Both backends hold the service key.
ALTER TABLE baitna_lead_listing_switches ENABLE ROW LEVEL SECURITY;


-- ============================================================================
-- 3. baitna_switch_listing
-- ============================================================================
-- Move an open inquiry onto a different unit from the same partner.
--
-- A function rather than a series of table writes for the same reason
-- baitna_create_lead is one: supabase-py cannot open a transaction, and the
-- quota check, the update and the log insert have to be one atomic step or two
-- taps on the button both pass the check and spend one switch each.
--
-- Consent is deliberately untouched. consent_events names the *partner* as the
-- counterparty, and the partner does not change here, so the record the student
-- already agreed to still describes exactly who receives their details. Minting
-- a second consent row would imply a new disclosure that is not happening.
--
--   BT005  lead not found, or not this student's
--   BT006  lead is closed, so its unit can no longer be changed
--   BT010  partner has acknowledged the lead, so its unit is settled
--   BT007  target listing missing, inactive, or belongs to another partner
--   BT008  target listing is already the one on the lead
--   BT009  switch quota spent (eligible date in DETAIL)
CREATE OR REPLACE FUNCTION baitna_switch_listing(
  p_student_id uuid,
  p_lead_id    uuid,
  p_listing_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_lead     baitna_leads%ROWTYPE;
  v_listing  baitna_listings%ROWTYPE;
  v_partner  baitna_partners%ROWTYPE;
  v_from     baitna_listings%ROWTYPE;
  v_used     integer;
  v_oldest   timestamptz;
  v_eligible date;
  v_now      timestamptz := now();

  -- The allowance, written once. It is returned to the caller as well as
  -- checked, and those two drifting apart would report a remaining count the
  -- function does not actually honour.
  c_limit    constant integer := 2;
BEGIN
  -- FOR UPDATE is what makes the quota hold. A second request for the same lead
  -- blocks here until the first commits, and then counts the row it wrote.
  SELECT * INTO v_lead
  FROM baitna_leads
  WHERE id = p_lead_id AND student_id = p_student_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Lead not found.' USING ERRCODE = 'BT005';
  END IF;

  -- Checked ahead of the closed catch-all so the student gets the accurate
  -- reason: an acknowledged inquiry is still live and can still be withdrawn,
  -- it just cannot be moved. The partner has read their details and started
  -- working that specific unit by this point.
  IF v_lead.status = 'acknowledged' THEN
    RAISE EXCEPTION
      'This partner has already responded to your inquiry, so its unit can no longer be changed.'
      USING ERRCODE = 'BT010';
  END IF;

  -- constants.SWITCH_ELIGIBLE_STATUSES, which is OPEN_STATUSES without
  -- 'acknowledged'. Narrower than the set withdraw accepts, on purpose.
  IF v_lead.status NOT IN ('submitted','posted_to_dashboard','aging') THEN
    RAISE EXCEPTION 'This inquiry is closed, so its unit can no longer be changed.'
      USING ERRCODE = 'BT006';
  END IF;

  IF v_lead.listing_id = p_listing_id THEN
    RAISE EXCEPTION 'That is already the unit on this inquiry.'
      USING ERRCODE = 'BT008';
  END IF;

  -- partner_id pinned to the lead's own: this endpoint can only ever move a
  -- student sideways within the partner they already consented to.
  --
  -- is_active is the only other bar, which is exactly what baitna_create_lead
  -- asks of a fresh submission. Availability is deliberately not checked: a
  -- student may join a waitlist unit on purpose, and switching is their own
  -- explicit choice. BOOKABLE_AVAILABILITY only governs the reroute, where the
  -- system picks the partner on their behalf.
  SELECT * INTO v_listing
  FROM baitna_listings
  WHERE id = p_listing_id
    AND partner_id = v_lead.partner_id
    AND is_active = true;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'That unit is not available from this partner.'
      USING ERRCODE = 'BT007';
  END IF;

  -- Rolling 30 days, measured per (student, partner) and not per lead, so
  -- closing one inquiry and opening another does not reset the allowance.
  SELECT count(*), min(switched_at) INTO v_used, v_oldest
  FROM baitna_lead_listing_switches
  WHERE student_id = p_student_id
    AND partner_id = v_lead.partner_id
    AND switched_at > v_now - interval '30 days';

  IF v_used >= c_limit THEN
    -- This function is the only writer and caps at 2, so the oldest of the two
    -- is always the one whose expiry frees the next switch.
    v_eligible := (v_oldest + interval '30 days')::date;
    RAISE EXCEPTION
      'You have already changed your unit twice with this partner. You can change it again after %.',
      v_eligible
      USING ERRCODE = 'BT009', DETAIL = v_eligible::text;
  END IF;

  SELECT * INTO v_from FROM baitna_listings WHERE id = v_lead.listing_id;

  UPDATE baitna_leads SET listing_id = p_listing_id WHERE id = v_lead.id;

  INSERT INTO baitna_lead_listing_switches (
    lead_id, student_id, partner_id, from_listing_id, to_listing_id, switched_at
  ) VALUES (
    v_lead.id, p_student_id, v_lead.partner_id, v_lead.listing_id, p_listing_id, v_now
  );

  -- Interest expressed in the new unit, counted the same way a fresh lead counts.
  -- The old unit is not decremented, matching baitna_bump_lead_count: a switch
  -- away was still interest, and decrementing makes browse ordering jitter.
  UPDATE baitna_listings SET lead_count = lead_count + 1 WHERE id = p_listing_id;

  SELECT * INTO v_partner FROM baitna_partners WHERE id = v_lead.partner_id;

  RETURN jsonb_build_object(
    'lead_id',             v_lead.id,
    'lead_reference',      v_lead.lead_reference,
    'partner_id',          v_partner.id,
    'partner_name',        v_partner.name,
    'property_name',       v_partner.property_name,
    'listing_id',          v_listing.id,
    'unit_type',           v_listing.unit_type,
    'previous_listing_id', v_from.id,
    'previous_unit_type',  v_from.unit_type,
    'switches_used',       v_used + 1,
    'switches_remaining',  c_limit - (v_used + 1),
    'switched_at',         v_now
  );
END;
$$;

-- Service role only, like baitna_create_lead: the anon key ships inside the
-- mobile app and must not be able to move anyone's inquiry.
REVOKE ALL ON FUNCTION baitna_switch_listing(uuid, uuid, uuid)
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION baitna_switch_listing(uuid, uuid, uuid) TO service_role;


-- ============================================================================
-- 4. POST-APPLY CHECKS
-- ============================================================================
-- Run on staging after applying, against a student with one open lead.
--
-- (a) SELECT baitna_switch_listing(<student>, <lead>, <another listing, same partner>);
--     -> switches_remaining 1, and baitna_leads.listing_id has moved
-- (b) repeat with a third listing        -> switches_remaining 0
-- (c) repeat once more                   -> BT009, DETAIL = eligible date
-- (d) pass the listing already on the lead -> BT008
-- (e) pass a listing from another partner  -> BT007
-- (f) UPDATE baitna_leads SET status='acknowledged'; retry -> BT010
-- (g) UPDATE baitna_leads SET status='withdrawn'; retry -> BT006
-- (h) pass another student's lead id        -> BT005
-- (i) SELECT unit_type FROM baitna_partner_lead_rows WHERE id = <lead>;
--     the dashboard view follows the switch with no extra write
-- (j) SELECT domain, latitude, longitude FROM university_domains;
--     the 18 seeded domains carry coordinates, any others are NULL
