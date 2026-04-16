"""
Authentication Service

Auth flow:
  SIGN UP:  send_otp → verify_otp → complete_registration
  LOGIN:    login (email + password)

Single-device enforcement uses device_id binding, not a logged_in flag lock.
On each new login the device_id is updated — the old device gets a 403 on its
next authenticated request because the stored device_id no longer matches.
"""
import secrets
import random
import string
import logging
import uuid
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from app.core.database import get_supabase_client, create_fresh_supabase_client
from app.core.redis import redis_manager
from app.core.email import email_service
from app.modules.auth.schemas import RegisterRequest, ProfileUpdateRequest, UserStats

logger = logging.getLogger(__name__)


class AuthService:
    """Handles all authentication operations."""

    # ------------------------------------------------------------------
    # OTP (sign-up student verification only)
    # ------------------------------------------------------------------

    async def send_otp(self, email: str) -> Dict[str, str]:
        """Send a 6-digit OTP to the user's university email."""
        try:
            domain = email.split("@")[1]
        except IndexError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email format")

        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database connection error")

        # University domain check (non-blocking — comment out the raise to enforce strictly)
        try:
            result = supabase.table("university_domains").select("*").eq("domain", domain).execute()
            if not result.data:
                logger.warning(f"Domain {domain} not in university whitelist")
                # raise HTTPException(status_code=400, detail=f"Domain {domain} is not eligible.")
        except Exception as e:
            logger.error(f"Domain whitelist query error: {e}")

        # Generate and store OTP
        otp_code = "".join(random.choices(string.digits, k=6))
        redis_key = f"sv:app:auth:otp:{email}"
        try:
            success = redis_manager.setex(redis_key, 300, otp_code)
            if not success:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate verification code")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Redis error: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate verification code")

        # Send email
        try:
            email_service.send_otp_email(email, otp_code, expiry_minutes=5)
        except Exception as e:
            redis_manager.delete(redis_key)
            logger.error(f"Failed to send OTP email: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to send verification code")

        return {"message": "OTP sent"}

    async def verify_otp(self, email: str, code: str, device_id: str = "") -> Dict[str, Any]:
        """
        Verify OTP for NEW user sign-up only.

        If the email already has an account, returns 409 — existing users
        must use the /login endpoint with their password.
        """
        redis_key = f"sv:app:auth:otp:{email}"

        # 1. Validate OTP from Redis
        stored_code = redis_manager.get(redis_key)
        if not stored_code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired or invalid")
        if stored_code != code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid access code")

        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database connection error")

        # 2. Reject if account already exists (OTP is sign-up only)
        try:
            existing = supabase.table("users").select("id").eq("email", email).execute()
            if existing.data:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An account with this email already exists. Please use the login screen."
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"User existence check failed: {e}")

        # 3. Create user in Supabase Auth (fresh client — never contaminate admin client)
        auth_client = create_fresh_supabase_client()
        if not auth_client:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database connection error")

        # Temporary password — will be replaced by chosen password in complete_registration
        temp_password = secrets.token_urlsafe(32)
        try:
            auth_response = auth_client.auth.sign_up({"email": email, "password": temp_password})
        except Exception as e:
            logger.error(f"Supabase sign_up failed: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create account. Please try again.")

        if not auth_response or not auth_response.user:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create account")

        if not auth_response.session or not auth_response.session.access_token:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Account created but no session returned. Ensure email confirmation is disabled in Supabase."
            )

        user_id = str(auth_response.user.id)
        access_token = auth_response.session.access_token

        # 4. Insert into public.users
        try:
            supabase.table("users").insert({
                "id": user_id,
                "email": email,
                "account_type": "free"
            }).execute()
            logger.info(f"Created user in public.users: {email}")
        except Exception as e:
            logger.error(f"Failed to insert user into public.users: {e}")
            # Roll back the Supabase Auth user so it's not orphaned
            try:
                supabase.auth.admin.delete_user(user_id)
            except Exception:
                pass
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create user profile. Please try again.")

        # 5. Consume the OTP
        redis_manager.delete(redis_key)

        return {
            "status": "success",
            "message": "OTP verified. Please complete your registration.",
            "access_token": access_token,
            "token_type": "bearer",
            "is_new_user": True,
            "user": {"id": user_id, "email": email}
        }

    # ------------------------------------------------------------------
    # Forgot Password Flow
    # ------------------------------------------------------------------

    async def forgot_password_send_otp(self, email: str) -> Dict[str, str]:
        """Send OTP for forgot password. Verifies the user exists first."""
        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database connection error")

        existing = supabase.table("users").select("id").eq("email", email).execute()
        if not existing.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No account found with this email."
            )

        # Uses the exact same send_otp logic to generate and send
        return await self.send_otp(email)

    async def forgot_password_verify_otp(self, email: str, code: str) -> Dict[str, Any]:
        """Verify OTP for forgot password and issue a temporary reset token."""
        redis_key = f"sv:app:auth:otp:{email}"
        stored_code = redis_manager.get(redis_key)
        
        if not stored_code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired or invalid")
        if stored_code != code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid access code")

        # Create a unique 10-minute reset token
        reset_token = str(uuid.uuid4())
        redis_manager.setex(f"sv:app:auth:reset_token:{email}", 600, reset_token)
        redis_manager.delete(redis_key)

        return {"reset_token": reset_token}

    async def forgot_password_reset(self, email: str, reset_token: str, new_password: str) -> Dict[str, Any]:
        """Use the temporary reset token to set a new password via Supabase Auth Admin API."""
        token_key = f"sv:app:auth:reset_token:{email}"
        stored_token = redis_manager.get(token_key)
        
        if not stored_token or stored_token != reset_token:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")
            
        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database connection error")
            
        user_check = supabase.table("users").select("id").eq("email", email).execute()
        if not user_check.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            
        user_id = str(user_check.data[0]["id"])
        
        try:
            supabase.auth.admin.update_user_by_id(user_id, {"password": new_password})
            logger.info(f"Password reset successfully for user: {user_id}")
        except Exception as e:
            logger.error(f"Failed to reset password for user {user_id}: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to reset password")
            
        redis_manager.delete(token_key)
        return {"message": "Password reset successfully"}

    # ------------------------------------------------------------------
    # Registration (profile completion after OTP)
    # ------------------------------------------------------------------

    async def complete_registration(self, user_id: str, request: RegisterRequest, access_token: str = None) -> Dict[str, Any]:
        """
        Complete registration by:
        1. Setting the user's chosen password in Supabase Auth (FATAL if fails)
        2. Saving profile fields to public.users
        """
        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database connection error")

        try:
            # --- Step 1: Set chosen password (abort if this fails) ---
            # IMPORTANT: admin.update_user_by_id with a new password INVALIDATES all
            # existing Supabase sessions for this user. We must re-sign-in immediately
            # after to get a fresh token, which the frontend will store.
            password_to_set = request.password
            new_access_token = None
            if password_to_set:
                try:
                    supabase.auth.admin.update_user_by_id(user_id, {"password": password_to_set})
                    logger.info(f"Password set for user: {user_id}")
                except Exception as pw_err:
                    logger.error(f"Failed to set password for user {user_id}: {pw_err}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to set account password. Please try again."
                    )

                # Re-authenticate to get a fresh token (old one was invalidated above)
                try:
                    auth_client = create_fresh_supabase_client()
                    if auth_client:
                        sign_in = auth_client.auth.sign_in_with_password({
                            "email": request.email,
                            "password": password_to_set
                        })
                        if sign_in and sign_in.session:
                            new_access_token = sign_in.session.access_token
                            logger.info(f"Re-authenticated after password set for: {user_id}")
                except Exception as reauth_err:
                    logger.error(f"Re-auth after password set failed: {reauth_err}")
                    # Non-fatal here — profile will still save, but frontend must handle token

            # --- Step 2: Build DB update payload ---
            # Only send columns that actually exist in public.users
            ALLOWED_DB_FIELDS = {
                "first_name", "last_name", "name", "nationality", "university",
                "phone_number", "age", "date_of_birth", "student_id", "device_id"
            }

            raw_data = request.model_dump(exclude_unset=True, by_alias=True)
            raw_data.pop("email", None)
            raw_data.pop("password", None)
            avatar_url = raw_data.pop("avatar_url", None)  # handled separately (alias field)

            update_data = {k: v for k, v in raw_data.items() if k in ALLOWED_DB_FIELDS}
            update_data["account_type"] = "free"
            update_data["logged_in"] = True
            if avatar_url:
                update_data["avatar_url"] = avatar_url

            # --- Step 3: Update public.users ---
            result = supabase.table("users").update(update_data).eq("id", user_id).execute()
            if not result.data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User profile not found. Please verify OTP first.")

            logger.info(f"Registration completed for user: {user_id}")
            profile = result.data[0]
            # Include fresh token (password update invalidated the old one)
            if new_access_token:
                profile["access_token"] = new_access_token
                profile["token_type"] = "bearer"
            return profile

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Registration completion error: {e}")
            if "unique" in str(e).lower() and "email" in str(e).lower():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already associated with another profile")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update profile: {str(e)}")

    # ------------------------------------------------------------------
    # Login (email + password — no OTP needed)
    # ------------------------------------------------------------------

    async def login(self, email: str, password: str, device_id: str = "") -> Dict:
        """
        Authenticate with email + password.

        Single-device enforcement: on success, device_id is updated to the
        current device. The previous device will receive a 403 on its next
        authenticated request because its device_id no longer matches.

        No 409 is ever raised here — a user can always log back in from a
        new device using their correct credentials.
        """
        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database connection error")

        # 1. Confirm user has a completed account in public.users
        try:
            user_check = supabase.table("users").select("id, email").eq("email", email).execute()
            if not user_check.data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No account found with this email. Please sign up first.")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"User lookup error during login: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error during login")

        # 2. Sign in via Supabase Auth (fresh client to avoid polluting admin singleton)
        auth_client = create_fresh_supabase_client()
        if not auth_client:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database connection error")

        try:
            auth_response = auth_client.auth.sign_in_with_password({"email": email, "password": password})
        except Exception as e:
            logger.error(f"Supabase sign_in_with_password error: {e}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

        if not auth_response or not auth_response.user or not auth_response.session:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

        user_id = str(auth_response.user.id)
        access_token = auth_response.session.access_token

        # 3. Update device_id → kicks out old device (it gets 403 on next request)
        try:
            update_payload: dict = {"logged_in": True}
            if device_id:
                update_payload["device_id"] = device_id
            supabase.table("users").update(update_payload).eq("id", user_id).execute()
            logger.info(f"User logged in: {email}, device: {device_id or 'unknown'}")
        except Exception as e:
            logger.error(f"Failed to update login state: {e}")

        return {
            "status": "success",
            "message": "Login successful",
            "access_token": access_token,
            "token_type": "bearer",
            "user": {"id": user_id, "email": email}
        }

    # ------------------------------------------------------------------
    # Profile & Analytics
    # ------------------------------------------------------------------

    async def update_profile(self, user_id: str, request: ProfileUpdateRequest) -> Dict[str, Any]:
        """Update allowed user profile fields."""
        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Database connection error")

        try:
            update_data = request.model_dump(exclude_unset=True, by_alias=True)
            if not update_data:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")
            result = supabase.table("users").update(update_data).eq("id", user_id).execute()
            if not result.data:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
            return result.data[0]
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Update profile error: {e}")
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))

    async def get_user_analytics(self, user_id: str) -> UserStats:
        """Calculate user analytics from redemptions."""
        supabase = get_supabase_client()
        try:
            response = supabase.table("redemptions") \
                .select("discount_amount, total_bill_amount, final_amount") \
                .eq("user_id", user_id) \
                .eq("is_voided", False) \
                .execute()
            data = response.data
            total_saved = sum(float(r.get("discount_amount", 0)) for r in data)
            total_spent = sum(float(r.get("total_bill_amount", 0)) for r in data)
            total_redemptions = len(data)

            user_res = supabase.table("users").select("account_type").eq("id", user_id).execute()
            sub_status = "free"
            if user_res.data:
                sub_status = user_res.data[0].get("account_type", "free")

            return UserStats(
                total_saved=total_saved,
                total_spent=total_spent,
                total_redemptions=total_redemptions,
                subscription_status=sub_status
            )
        except Exception as e:
            logger.error(f"Analytics error: {e}")
            return UserStats()

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    async def logout_user(self, user_id: str, access_token: str = None) -> None:
        """
        Log out user:
        1. Clear logged_in and device_id in public.users
        2. Attempt to invalidate the Supabase JWT so it cannot be reused
        """
        supabase = get_supabase_client()
        if not supabase:
            return

        # Clear session state in DB (device_id cleared → old token gets 403 if somehow reused)
        try:
            supabase.table("users").update({"logged_in": False, "device_id": None}).eq("id", user_id).execute()
            logger.info(f"User logged out: {user_id}")
        except Exception as e:
            logger.error(f"Logout DB update error: {e}")

        # Invalidate the JWT in Supabase so it can't be reused for the remaining 1hr window
        if access_token:
            try:
                supabase.auth.admin.sign_out(access_token)
                logger.info(f"Supabase JWT invalidated for user: {user_id}")
            except Exception as e:
                # Non-fatal — device_id clearing already handles security
                logger.error(f"Failed to invalidate Supabase JWT: {e}")

    # ------------------------------------------------------------------
    # Account Deletion (permanent)
    # ------------------------------------------------------------------

    async def delete_account(self, user_id: str, access_token: str = None) -> None:
        """
        Permanently delete a user account and all associated data.

        Deletion order (most-dependent first to avoid FK violations):
        1. redemptions       (references user_id, no CASCADE)
        2. entitlements       (references user_id)
        3. ticket_records     (references user_id, no FK constraint)
        4. public.users       (fetch stripe_customer_id + email first)
        5. Stripe customer    (best-effort, non-fatal)
        6. Redis keys         (OTP, reset tokens, Orbit conversations)
        7. Supabase Auth JWT  (invalidate current session)
        8. Supabase Auth user (auth.users row — final step)
        """
        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection error"
            )

        # ── Fetch user info before deletion (need email + stripe ID) ──
        email = None
        stripe_customer_id = None
        try:
            user_result = supabase.table("users").select("email, stripe_customer_id").eq("id", user_id).execute()
            if user_result.data:
                email = user_result.data[0].get("email")
                stripe_customer_id = user_result.data[0].get("stripe_customer_id")
        except Exception as e:
            logger.error(f"Failed to fetch user before deletion: {e}")
            # Continue — we can still delete by user_id

        # ── 1. Delete redemptions ──
        try:
            supabase.table("redemptions").delete().eq("user_id", user_id).execute()
            logger.info(f"Deleted redemptions for user: {user_id}")
        except Exception as e:
            logger.error(f"Failed to delete redemptions for user {user_id}: {e}")

        # ── 2. Delete entitlements ──
        try:
            supabase.table("entitlements").delete().eq("user_id", user_id).execute()
            logger.info(f"Deleted entitlements for user: {user_id}")
        except Exception as e:
            logger.error(f"Failed to delete entitlements for user {user_id}: {e}")

        # ── 3. Delete ticket_records ──
        try:
            supabase.table("ticket_records").delete().eq("user_id", user_id).execute()
            logger.info(f"Deleted ticket_records for user: {user_id}")
        except Exception as e:
            logger.error(f"Failed to delete ticket_records for user {user_id}: {e}")

        # ── 4. Delete public.users row ──
        try:
            supabase.table("users").delete().eq("id", user_id).execute()
            logger.info(f"Deleted public.users row for user: {user_id}")
        except Exception as e:
            logger.error(f"Failed to delete public.users row for user {user_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete account. Please try again."
            )

        # ── 5. Delete Stripe customer (best-effort) ──
        if stripe_customer_id:
            try:
                import stripe
                stripe.Customer.delete(stripe_customer_id)
                logger.info(f"Deleted Stripe customer {stripe_customer_id} for user: {user_id}")
            except Exception as e:
                logger.error(f"Failed to delete Stripe customer {stripe_customer_id}: {e}")

        # ── 6. Clean up Redis keys ──
        if email:
            try:
                redis_manager.delete(f"sv:app:auth:otp:{email}")
                redis_manager.delete(f"sv:app:auth:reset_token:{email}")
            except Exception as e:
                logger.error(f"Failed to clean up Redis auth keys for {email}: {e}")

        # Clean up Orbit conversation and daily claim keys via pattern scan
        try:
            rc = redis_manager.redis_client
            if rc:
                # Orbit conversations
                for key in rc.scan_iter(match=f"orbit:conversation:{user_id}:*", count=100):
                    rc.delete(key)
                # Daily claim tracking
                for key in rc.scan_iter(match=f"sv:app:claim:daily:{user_id}:*", count=100):
                    rc.delete(key)
                logger.info(f"Cleaned up Redis ephemeral keys for user: {user_id}")
        except Exception as e:
            logger.error(f"Failed to clean up Redis ephemeral keys for user {user_id}: {e}")

        # ── 7. Invalidate current JWT ──
        if access_token:
            try:
                supabase.auth.admin.sign_out(access_token)
                logger.info(f"Invalidated JWT for deleted user: {user_id}")
            except Exception as e:
                logger.error(f"Failed to invalidate JWT for deleted user {user_id}: {e}")

        # ── 8. Delete Supabase Auth user (final step) ──
        try:
            supabase.auth.admin.delete_user(user_id)
            logger.info(f"Deleted Supabase Auth user: {user_id}")
        except Exception as e:
            logger.error(f"Failed to delete Supabase Auth user {user_id}: {e}")
            # This is serious but the public.users row is already gone,
            # so the account is effectively unusable. Log for manual cleanup.

        logger.info(f"Account permanently deleted: {user_id} ({email})")


# Singleton instance
auth_service = AuthService()
