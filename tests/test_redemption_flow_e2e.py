"""
End-to-End System Tests for Redemption Flow (Phase A)
Tests all 12 manual API and business logic rules against the active dev database.
"""

import asyncio
import os
import hashlib
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

from app.modules.merchant.service import merchant_service
from app.modules.entitlements.service import entitlement_service
from app.modules.merchant.router import (
    shift_login,
    shift_logout,
    validate_qr_token,
    confirm_redemption as router_confirm
)
from app.modules.merchant.schemas import (
    ShiftLoginRequest,
    MerchantValidateRequest,
    MerchantConfirmRequest
)
from app.modules.entitlements.schemas import EntitlementStatusResponse
from app.shared.enums import EntitlementState
from app.shared.constants import (
    REDIS_PREFIX_SHIFT_SESSION,
    REDIS_PREFIX_QR_TOKEN,
    REDIS_PREFIX_BACKUP_CODE
)

PASS = "✅ PASS"
FAIL = "❌ FAIL"

results = []

def record(test_num, name, success, details=""):
    status_str = PASS if success else FAIL
    results.append((test_num, name, status_str, details))
    print(f"[{status_str}] Test {test_num}: {name} - {details}")


async def run_all_tests():
    print("\n=======================================================")
    print("🚀 STARTING FULL SYSTEM E2E REDEMPTION FLOW TESTS")
    print("=======================================================\n")

    supabase = merchant_service.supabase
    redis = merchant_service.redis

    # -------------------------------------------------------------
    # 0. SETUP TEST MERCHANT, OFFER, AND STUDENT USER
    # -------------------------------------------------------------
    test_user_id = "9fa703a2-929f-462a-a9b9-f85eac6dc400" # b00114382@aus.edu
    test_pin = "1234"
    pin_hash = hashlib.sha256(test_pin.encode()).hexdigest()

    # Get or create test merchant
    m_res = supabase.table("merchants").select("*").limit(1).execute()
    if not m_res.data:
        print("❌ Cannot run tests: No merchants found in DB")
        return
    merchant = m_res.data[0]
    merchant_id = merchant["id"]
    merchant_name = merchant["name"]

    # Set known PIN for test
    supabase.table("merchants").update({"pin_hash": pin_hash}).eq("id", merchant_id).execute()

    # Create/get test offer with 20% discount
    offer_data = {
        "title": "E2E Test 20% Offer",
        "description": "Offer created for E2E redemption test",
        "merchant_id": merchant_id,
        "offer_type": "percentage",
        "discount_value": "20%",
        "valid_from": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        "valid_until": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        "is_active": True,
        "frequency_per_student": "daily",
        "fulfilment_type": "both"
    }
    created_offer = supabase.table("offers").insert(offer_data).execute().data[0]
    offer_id = created_offer["id"]

    try:
        # -------------------------------------------------------------
        # TEST 1: POST /merchant/shift/login with valid PIN
        # -------------------------------------------------------------
        shift_req = ShiftLoginRequest(merchant_id=merchant_id, pin=test_pin)
        login_res = await shift_login(shift_req)
        session_token = login_res.session_token

        # Verify Redis key was created
        redis_has_session = redis.get(f"{REDIS_PREFIX_SHIFT_SESSION}{session_token}") is not None
        record(1, "Shift Login with valid PIN", login_res.success and redis_has_session, f"Token: {session_token[:10]}...")

        # -------------------------------------------------------------
        # TEST 2: POST /merchant/shift/login with WRONG PIN
        # -------------------------------------------------------------
        try:
            wrong_req = ShiftLoginRequest(merchant_id=merchant_id, pin="9999")
            await shift_login(wrong_req)
            record(2, "Shift Login with wrong PIN rejects", False, "Expected 401 but succeeded")
        except Exception as e:
            record(2, "Shift Login with wrong PIN rejects", True, f"Rejected as expected: {e}")

        # -------------------------------------------------------------
        # TEST 3: Claim offer & generate proof token + backup code
        # -------------------------------------------------------------
        entitlement = await entitlement_service.claim_entitlement(test_user_id, offer_id)
        entitlement_id = str(entitlement.entitlement_id)
        proof_res = await entitlement_service.generate_proof_token(entitlement_id, test_user_id)
        proof_token = proof_res.proof_token
        backup_code = proof_res.backup_code

        valid_backup = (
            backup_code is not None 
            and len(backup_code) == 4 
            and proof_token is not None
        )
        record(3, "Generate QR proof token + 4-char backup code", valid_backup, f"Backup Code: {backup_code}")

        # -------------------------------------------------------------
        # TEST 4: POST /merchant/validate with BACKUP CODE
        # -------------------------------------------------------------
        val_req = MerchantValidateRequest(backup_code=backup_code)
        val_res = await validate_qr_token(val_req, x_shift_token=session_token)
        record(4, "Validate via 4-char backup code", val_res.success and val_res.status == "PASS", f"Status: {val_res.status}")

        # -------------------------------------------------------------
        # TEST 5: GET /entitlements/{id}/status after scan (AMBER UI)
        # -------------------------------------------------------------
        status_amber = await entitlement_service.get_entitlement_status(entitlement_id, test_user_id)
        record(5, "Student UI state is AMBER while pending confirmation", status_amber.ui_state == "amber", f"ui_state: {status_amber.ui_state}")

        # -------------------------------------------------------------
        # TEST 6: POST /merchant/validate with EXPIRED / INVALID session token
        # -------------------------------------------------------------
        val_res_bad_session = await validate_qr_token(val_req, x_shift_token="invalid_expired_token_xyz")
        record(6, "Validate with invalid shift token fails", val_res_bad_session.status == "FAIL", f"Reason: {val_res_bad_session.reason}")

        # -------------------------------------------------------------
        # TEST 7: POST /merchant/confirm with bill amount (No PIN required)
        # -------------------------------------------------------------
        conf_req = MerchantConfirmRequest(
            proof_token=backup_code,
            total_bill_amount=Decimal("100.00")
        )
        conf_res = await router_confirm(conf_req, x_shift_token=session_token)

        # Check DB redemption row has commission_tier = 20 (since 20% discount)
        redemption_row = supabase.table("redemptions").select("*").eq("id", str(conf_res.redemption_id)).execute().data[0]
        correct_tier = redemption_row.get("commission_tier") == 20

        # Check both Redis keys deleted
        qr_key_deleted = redis.get(f"{REDIS_PREFIX_QR_TOKEN}{proof_token}") is None
        backup_key_deleted = redis.get(f"{REDIS_PREFIX_BACKUP_CODE}{backup_code}") is None

        record(7, "Confirm redemption with bill & tier calculation", 
               conf_res.success and correct_tier and qr_key_deleted and backup_key_deleted,
               f"Tier: {redemption_row.get('commission_tier')}, Final bill: {conf_res.final_amount}")

        # -------------------------------------------------------------
        # TEST 8: GET /entitlements/{id}/status after confirm (GREEN UI)
        # -------------------------------------------------------------
        status_green = await entitlement_service.get_entitlement_status(entitlement_id, test_user_id)
        record(8, "Student UI state is GREEN with bill breakdown after confirm", 
               status_green.ui_state == "green" and status_green.savings == Decimal("20.00"),
               f"ui_state: {status_green.ui_state}, savings: AED {status_green.savings}")

        # -------------------------------------------------------------
        # TEST 9: Verify single-use (cannot validate confirmed entitlement again)
        # -------------------------------------------------------------
        val_again = await validate_qr_token(val_req, x_shift_token=session_token)
        record(9, "Single-use enforcement: re-validating confirmed token fails", val_again.status == "FAIL", f"Status: {val_again.status}")

        # -------------------------------------------------------------
        # TEST 10: Merchant Control 3 (Frequency Limit: weekly)
        # -------------------------------------------------------------
        # Update offer to weekly frequency
        supabase.table("offers").update({"frequency_per_student": "weekly"}).eq("id", offer_id).execute()
        offer_weekly = supabase.table("offers").select("*").eq("id", offer_id).execute().data[0]

        # Since student just confirmed today, claiming again this week should fail
        try:
            await entitlement_service.claim_entitlement(test_user_id, offer_id)
            record(10, "Frequency limit (weekly) blocks second claim in same week", False, "Expected rejection but succeeded")
        except ValueError as e:
            record(10, "Frequency limit (weekly) blocks second claim in same week", True, f"Blocked: {e}")

        # -------------------------------------------------------------
        # TEST 11: Merchant Control 2 (Daily Redemption Cap)
        # -------------------------------------------------------------
        # Set daily cap to 1 (since 1 redemption already happened today)
        supabase.table("offers").update({"frequency_per_student": "daily", "daily_redemption_cap": 1}).eq("id", offer_id).execute()
        try:
            # Another user (or clean claim attempt)
            another_user = "80695bf4-5ad6-4662-abb8-2b3d4f302e16"
            await entitlement_service.claim_entitlement(another_user, offer_id)
            record(11, "Daily venue cap blocks claim when cap is reached", False, "Expected daily cap rejection but succeeded")
        except ValueError as e:
            record(11, "Daily venue cap blocks claim when cap is reached", True, f"Blocked: {e}")

        # -------------------------------------------------------------
        # TEST 12: POST /merchant/shift/logout terminates session
        # -------------------------------------------------------------
        from app.modules.merchant.schemas import ShiftLogoutRequest
        await shift_logout(ShiftLogoutRequest(session_token=session_token))
        session_exists = redis.get(f"{REDIS_PREFIX_SHIFT_SESSION}{session_token}") is not None
        record(12, "Shift Logout clears session in Redis", not session_exists, "Session key deleted")

    finally:
        # Cleanup test offer
        supabase.table("redemptions").delete().eq("offer_id", offer_id).execute()
        supabase.table("entitlements").delete().eq("offer_id", offer_id).execute()
        supabase.table("offers").delete().eq("id", offer_id).execute()

    print("\n=======================================================")
    print("📊 TEST SUMMARY REPORT")
    print("=======================================================\n")
    all_passed = True
    for num, name, status, details in results:
        print(f"Test {num:2d}: {status} | {name} ({details})")
        if status != PASS:
            all_passed = False

    print("\n" + ("🎉 ALL 12 REDEMPTION FLOW TESTS PASSED!" if all_passed else "❌ SOME TESTS FAILED"))
    print("=======================================================\n")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
