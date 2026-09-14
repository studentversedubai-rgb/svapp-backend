-- Verification for 20260914_add_baitna_switch_and_distance.sql.
--
-- Run this in the Supabase SQL Editor AFTER applying that migration. It builds
-- its own throwaway partner and listings, exercises every branch of
-- baitna_switch_listing against them, and deletes everything it made. Nothing
-- belonging to a real partner or student is written to or removed.
--
-- SET ONE THING FIRST: replace the email on the marked line with a real student
-- from public.users. The lead has to hang off a genuine user row because
-- baitna_leads.student_id is a foreign key onto it.
--
-- Read the results grid at the end: every row should say ok = true.


-- ============================================================================
-- SETUP
-- ============================================================================

DROP TABLE IF EXISTS baitna_switch_test_results;
CREATE TABLE baitna_switch_test_results (
  seq      serial primary key,
  step     text,
  expected text,
  got      text,
  ok       boolean
);

DO $test$
DECLARE
  -- >>> CHANGE THIS to a real student email from public.users <<<
  c_student_email  text := 'student@example.edu';

  v_student   uuid;
  v_stranger  uuid := gen_random_uuid();   -- a student id that owns nothing
  v_partner   uuid;
  v_other     uuid;
  v_l1        uuid;
  v_l2        uuid;
  v_l3        uuid;
  v_foreign   uuid;
  v_lead      uuid;
  v_consent   uuid;
  v_res       jsonb;
  v_state     text;
  v_detail    text;
  v_count     integer;
  v_text      text;

  -- A failure lands in the results table rather than aborting, so the cleanup
  -- below still runs and no test partner is left behind.
  v_error     text := NULL;

BEGIN

  SELECT id INTO v_student FROM users WHERE lower(email) = lower(c_student_email);
  IF v_student IS NULL THEN
    RAISE EXCEPTION
      'No user with email %. Edit c_student_email near the top of this script.',
      c_student_email;
  END IF;

  -- Leftovers from an interrupted previous run.
  DELETE FROM baitna_lead_listing_switches
   WHERE partner_id IN (SELECT id FROM baitna_partners
                         WHERE partner_code IN ('ZZTESTA','ZZTESTB'));
  DELETE FROM baitna_leads
   WHERE partner_id IN (SELECT id FROM baitna_partners
                         WHERE partner_code IN ('ZZTESTA','ZZTESTB'));
  DELETE FROM consent_events
   WHERE counterparty_ref IN (SELECT id FROM baitna_partners
                               WHERE partner_code IN ('ZZTESTA','ZZTESTB'));
  DELETE FROM baitna_partners WHERE partner_code IN ('ZZTESTA','ZZTESTB');

  -- The partner under test, plus a second one to prove a switch cannot cross
  -- partner boundaries. Coordinates set so the distance line has something to
  -- work with.
  INSERT INTO baitna_partners (name, property_name, partner_code,
                               notification_emails, price_disclosure_enabled,
                               is_signed, is_active, latitude, longitude)
  VALUES ('ZZ Switch Test Residences', 'ZZ Test Campus', 'ZZTESTA',
          ARRAY['nobody@example.invalid'], true, true, true, 25.0800, 55.1400)
  RETURNING id INTO v_partner;

  INSERT INTO baitna_partners (name, partner_code, notification_emails,
                               price_disclosure_enabled, is_signed, is_active)
  VALUES ('ZZ Other Partner', 'ZZTESTB', ARRAY['nobody@example.invalid'],
          true, true, true)
  RETURNING id INTO v_other;

  INSERT INTO baitna_listings (partner_id, unit_type, price_amount,
                               availability_status, occupancy_max, occupants_current)
  VALUES (v_partner, 'studio', 3500, 'available', 1, 0) RETURNING id INTO v_l1;

  INSERT INTO baitna_listings (partner_id, unit_type, price_amount,
                               availability_status, occupancy_max, occupants_current)
  VALUES (v_partner, 'en_suite', 2800, 'available', 1, 0) RETURNING id INTO v_l2;

  INSERT INTO baitna_listings (partner_id, unit_type, price_amount,
                               availability_status, occupancy_max, occupants_current)
  VALUES (v_partner, 'one_bed', 4800, 'available', 2, 0) RETURNING id INTO v_l3;

  INSERT INTO baitna_listings (partner_id, unit_type, price_amount,
                               availability_status, occupancy_max, occupants_current)
  VALUES (v_other, 'studio', 3100, 'available', 1, 0) RETURNING id INTO v_foreign;

  -- The inquiry everything below acts on.
  v_res := baitna_create_lead(
    v_student, v_partner, v_l1,
    (now() + interval '60 days')::date, 12, '3500_5000', 'arriving_soon',
    'baitna_v1', 'consent text as shown to the student', false,
    'privacy@example.invalid');

  v_lead := (v_res->>'id')::uuid;
  SELECT consent_event_id INTO v_consent FROM baitna_leads WHERE id = v_lead;


  -- ==========================================================================
  -- SCHEMA
  -- ==========================================================================

  SELECT count(*) INTO v_count
  FROM information_schema.columns
  WHERE table_schema = 'public' AND table_name = 'baitna_partners'
    AND column_name IN ('latitude','longitude');
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('partners have coordinate columns', '2', v_count::text, v_count = 2);

  SELECT count(*) INTO v_count
  FROM information_schema.columns
  WHERE table_schema = 'public' AND table_name = 'university_domains'
    AND column_name IN ('latitude','longitude');
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('universities have coordinate columns', '2', v_count::text, v_count = 2);

  SELECT count(*) INTO v_count
  FROM university_domains WHERE latitude IS NOT NULL AND longitude IS NOT NULL;
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('university coordinates seeded', '>= 1 (18 if the domain seed has run)',
     v_count::text, v_count >= 1);

  SELECT count(*) INTO v_count FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'baitna_switch_listing';
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('switch function exists', '1', v_count::text, v_count = 1);

  SELECT count(*) INTO v_count FROM pg_tables
  WHERE schemaname = 'public' AND tablename = 'baitna_lead_listing_switches'
    AND rowsecurity = true;
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('switch log has RLS enabled', '1', v_count::text, v_count = 1);

  -- The anon key ships inside the mobile app, so this one matters.
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    v_text := has_function_privilege(
      'anon', 'baitna_switch_listing(uuid,uuid,uuid)', 'EXECUTE')::text;
    INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
      ('anon cannot execute the function', 'false', v_text, v_text = 'false');
  END IF;

  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    v_text := has_function_privilege(
      'service_role', 'baitna_switch_listing(uuid,uuid,uuid)', 'EXECUTE')::text;
    INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
      ('service_role can execute the function', 'true', v_text, v_text = 'true');
  END IF;


  -- ==========================================================================
  -- REFUSALS THAT DO NOT SPEND THE ALLOWANCE
  -- ==========================================================================

  BEGIN
    PERFORM baitna_switch_listing(v_student, v_lead, v_l1);
    v_state := 'no error';
  EXCEPTION WHEN OTHERS THEN v_state := SQLSTATE;
  END;
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('switching to the unit already on the lead', 'BT008', v_state, v_state = 'BT008');

  BEGIN
    PERFORM baitna_switch_listing(v_student, v_lead, v_foreign);
    v_state := 'no error';
  EXCEPTION WHEN OTHERS THEN v_state := SQLSTATE;
  END;
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('switching to another partner''s unit', 'BT007', v_state, v_state = 'BT007');

  BEGIN
    PERFORM baitna_switch_listing(v_stranger, v_lead, v_l2);
    v_state := 'no error';
  EXCEPTION WHEN OTHERS THEN v_state := SQLSTATE;
  END;
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('someone else moving this lead', 'BT005', v_state, v_state = 'BT005');

  SELECT count(*) INTO v_count FROM baitna_lead_listing_switches WHERE lead_id = v_lead;
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('refusals logged nothing', '0', v_count::text, v_count = 0);


  -- ==========================================================================
  -- THE TWO SWITCHES A STUDENT GETS
  -- ==========================================================================

  v_res := baitna_switch_listing(v_student, v_lead, v_l2);
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('first switch leaves one remaining', '1',
     v_res->>'switches_remaining', (v_res->>'switches_remaining') = '1');
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('first switch reports the new unit', 'en_suite',
     v_res->>'unit_type', (v_res->>'unit_type') = 'en_suite');
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('first switch reports the old unit', 'studio',
     v_res->>'previous_unit_type', (v_res->>'previous_unit_type') = 'studio');

  SELECT listing_id::text INTO v_text FROM baitna_leads WHERE id = v_lead;
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('the lead actually moved', v_l2::text, v_text, v_text = v_l2::text);

  SELECT lead_reference INTO v_text FROM baitna_leads WHERE id = v_lead;
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('lead reference is unchanged', v_res->>'lead_reference', v_text,
     v_text = v_res->>'lead_reference');

  v_res := baitna_switch_listing(v_student, v_lead, v_l3);
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('second switch leaves none remaining', '0',
     v_res->>'switches_remaining', (v_res->>'switches_remaining') = '0');

  SELECT count(*) INTO v_count FROM baitna_lead_listing_switches WHERE lead_id = v_lead;
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('both switches logged', '2', v_count::text, v_count = 2);

  -- The whole point of doing this in the same lead rather than a new one.
  SELECT consent_event_id::text INTO v_text FROM baitna_leads WHERE id = v_lead;
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('consent record carried across untouched', v_consent::text, v_text,
     v_text = v_consent::text);

  SELECT count(*) INTO v_count FROM consent_events
   WHERE id = v_consent AND withdrawn_at IS NULL;
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('consent is still live', '1', v_count::text, v_count = 1);

  SELECT lead_count INTO v_count FROM baitna_listings WHERE id = v_l3;
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('the unit switched into gained a lead_count', '1', v_count::text, v_count = 1);

  -- The dashboard reads unit_type through a join, so it follows with no extra write.
  SELECT unit_type INTO v_text FROM baitna_partner_lead_rows WHERE id = v_lead;
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('partner dashboard shows the new unit', 'one_bed', v_text, v_text = 'one_bed');


  -- ==========================================================================
  -- THE THIRD SWITCH IS REFUSED
  -- ==========================================================================

  BEGIN
    PERFORM baitna_switch_listing(v_student, v_lead, v_l1);
    v_state := 'no error'; v_detail := NULL;
  EXCEPTION WHEN OTHERS THEN
    GET STACKED DIAGNOSTICS v_state = RETURNED_SQLSTATE, v_detail = PG_EXCEPTION_DETAIL;
  END;
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('third switch inside 30 days', 'BT009', v_state, v_state = 'BT009');
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('refusal carries an eligible date', 'an ISO date', coalesce(v_detail, '(none)'),
     v_detail ~ '^\d{4}-\d{2}-\d{2}$');

  SELECT listing_id::text INTO v_text FROM baitna_leads WHERE id = v_lead;
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('a refused switch changed nothing', v_l3::text, v_text, v_text = v_l3::text);


  -- ==========================================================================
  -- ACKNOWLEDGED AND CLOSED LEADS
  -- ==========================================================================

  -- Fresh lead so the quota is not what does the refusing here.
  DELETE FROM baitna_lead_listing_switches WHERE lead_id = v_lead;

  UPDATE baitna_leads SET status = 'acknowledged' WHERE id = v_lead;
  BEGIN
    PERFORM baitna_switch_listing(v_student, v_lead, v_l1);
    v_state := 'no error';
  EXCEPTION WHEN OTHERS THEN v_state := SQLSTATE;
  END;
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('acknowledged lead cannot be moved', 'BT010', v_state, v_state = 'BT010');

  UPDATE baitna_leads SET status = 'withdrawn' WHERE id = v_lead;
  BEGIN
    PERFORM baitna_switch_listing(v_student, v_lead, v_l1);
    v_state := 'no error';
  EXCEPTION WHEN OTHERS THEN v_state := SQLSTATE;
  END;
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('closed lead cannot be moved', 'BT006', v_state, v_state = 'BT006');

  SELECT (closed_at IS NOT NULL)::text INTO v_text FROM baitna_leads WHERE id = v_lead;
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('withdrawal still stamps closed_at', 'true', v_text, v_text = 'true');


EXCEPTION WHEN OTHERS THEN
  -- Remember the failure, fall through to cleanup, re-raise below.
  v_error := SQLSTATE || ': ' || SQLERRM;
  INSERT INTO baitna_switch_test_results (step, expected, got, ok) VALUES
    ('script ran to completion', 'no error', v_error, false);
END
$test$;


-- ============================================================================
-- CLEANUP — removes only what this script created
-- ============================================================================

DELETE FROM baitna_lead_listing_switches
 WHERE partner_id IN (SELECT id FROM baitna_partners
                       WHERE partner_code IN ('ZZTESTA','ZZTESTB'));

DELETE FROM baitna_leads
 WHERE partner_id IN (SELECT id FROM baitna_partners
                       WHERE partner_code IN ('ZZTESTA','ZZTESTB'));

DELETE FROM consent_events
 WHERE counterparty_ref IN (SELECT id FROM baitna_partners
                             WHERE partner_code IN ('ZZTESTA','ZZTESTB'));

-- Cascades to the listings and the reference sequences.
DELETE FROM baitna_partners WHERE partner_code IN ('ZZTESTA','ZZTESTB');


-- ============================================================================
-- RESULTS — every row should read ok = true
-- ============================================================================

SELECT
  CASE WHEN ok THEN 'PASS' ELSE 'FAIL' END AS result,
  step,
  expected,
  got
FROM baitna_switch_test_results
ORDER BY ok, seq;
