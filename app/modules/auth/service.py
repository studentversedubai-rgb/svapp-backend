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
import os
import mimetypes
from io import BytesIO
from datetime import date, datetime, timezone
from typing import Optional, Dict, Any
from fastapi import HTTPException, status, UploadFile
from app.core.database import get_supabase_client, create_fresh_supabase_client
from app.core.redis import redis_manager
from app.core.email import email_service
from app.modules.auth.schemas import RegisterRequest, ProfileUpdateRequest, UserStats

logger = logging.getLogger(__name__)
VERIFICATION_BUCKET_NAME = os.getenv("VERIFICATION_BUCKET_NAME", "user-verification-documents")
VERIFICATION_FILE_MAX_BYTES = int(os.getenv("VERIFICATION_FILE_MAX_BYTES", "10485760"))
PROFILE_IMAGE_BUCKET_NAME = os.getenv("PROFILE_IMAGE_BUCKET_NAME", "user-profile-images")
PROFILE_IMAGE_MAX_BYTES = int(os.getenv("PROFILE_IMAGE_MAX_BYTES", "5242880"))
ALLOWED_PROFILE_IMAGE_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class AuthService:
    """Handles all authentication operations."""

    ALLOWED_VERIFICATION_MIME_TYPES = {
        "application/pdf": ".pdf",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/jpg": ".jpg",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    }

    def _normalize_email(self, email: str) -> str:
        return email.strip().lower()

    def _extract_auth_user_id(self, auth_user: Any) -> str:
        if hasattr(auth_user, "id") and getattr(auth_user, "id"):
            return str(getattr(auth_user, "id"))
        if isinstance(auth_user, dict) and auth_user.get("id"):
            return str(auth_user["id"])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create account. Please try again.",
        )

    def _find_auth_user_id_by_email(self, supabase: Any, email: str) -> Optional[str]:
        """Paginate supabase auth admin users to locate an existing user_id by email."""
        target = email.strip().lower()
        try:
            page = 1
            per_page = 200
            while True:
                result = supabase.auth.admin.list_users(page=page, per_page=per_page)
                users = result if isinstance(result, list) else getattr(result, "users", None) or []
                if not users:
                    return None
                for u in users:
                    u_email = (getattr(u, "email", None) or (u.get("email") if isinstance(u, dict) else None) or "").lower()
                    if u_email == target:
                        u_id = getattr(u, "id", None) or (u.get("id") if isinstance(u, dict) else None)
                        return str(u_id) if u_id else None
                if len(users) < per_page:
                    return None
                page += 1
                if page > 50:  # safety cap
                    return None
        except Exception as e:
            logger.error(f"Auth user lookup by email failed for {target}: {e}")
            return None

    def _build_review_error_detail(self, user: Dict[str, Any]) -> Dict[str, Any]:
        verification_status = user.get("verification_status") or "pending_review"
        reason = user.get("verification_rejection_reason")

        if verification_status == "suspended":
            return {
                "code": "ACCOUNT_SUSPENDED",
                "message": (
                    "Your account was suspended due to repeated rejections. "
                    "Please email support@studentverse.ae to rectify this."
                ),
                "verification_status": "suspended",
                "review_reason": reason,
            }

        if verification_status == "rejected":
            return {
                "code": "ACCOUNT_REJECTED",
                "message": "Your account review needs updated documents before you can log in.",
                "verification_status": "rejected",
                "review_reason": reason,
            }

        return {
            "code": "ACCOUNT_PENDING_REVIEW",
            "message": "Your account is still under review.",
            "verification_status": "pending_review",
            "review_reason": reason,
        }

    def _resolve_user_by_any_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Look up a public.users row where either users.email OR users.personal_email
        matches the supplied address. Returns the raw row dict or None.

        Used by forgot-password so users can type either email they know.
        """
        normalized = self._normalize_email(email)
        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection error",
            )
        try:
            result = (
                supabase.table("users")
                .select("id, email, personal_email")
                .or_(f"email.eq.{normalized},personal_email.eq.{normalized}")
                .limit(1)
                .execute()
            )
        except Exception as e:
            logger.error(f"User resolve by any email failed for {normalized}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error",
            )
        return result.data[0] if result.data else None

    def _domain_is_university(self, email: str) -> bool:
        """True if the email's domain is registered in university_domains."""
        try:
            domain = self._normalize_email(email).split("@", 1)[1]
        except IndexError:
            return False
        supabase = get_supabase_client()
        if not supabase:
            return False
        try:
            result = (
                supabase.table("university_domains")
                .select("domain")
                .eq("domain", domain)
                .eq("is_active", True)
                .limit(1)
                .execute()
            )
        except Exception as e:
            logger.error(f"Domain lookup failed for {domain}: {e}")
            return False
        return bool(result.data)

    def _lookup_verified_university(self, email: str) -> str:
        normalized_email = self._normalize_email(email)
        try:
            domain = normalized_email.split("@", 1)[1]
        except IndexError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email format")

        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection error",
            )

        try:
            domain_result = (
                supabase.table("university_domains")
                .select("university_name")
                .eq("domain", domain)
                .eq("is_active", True)
                .execute()
            )
        except Exception as e:
            logger.error(f"University domain lookup error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to verify university domain",
            )

        if not domain_result.data:
            logger.warning(f"Unsupported university domain: {domain} (email: {normalized_email})")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Your university is not supported yet. Only verified UAE university email domains are accepted.",
            )

        return domain_result.data[0]["university_name"]

    def _parse_date_of_birth(self, date_of_birth: str) -> tuple[str, int]:
        try:
            parsed = datetime.strptime(date_of_birth.strip(), "%Y-%m-%d").date()
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="date_of_birth must be in YYYY-MM-DD format",
            )

        today = date.today()
        age = today.year - parsed.year - (
            (today.month, today.day) < (parsed.month, parsed.day)
        )

        if age < 18:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You must be at least 18 years old to register.",
            )

        if age > 120:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid date of birth.",
            )

        return parsed.isoformat(), age

    async def _read_verification_file(self, upload: UploadFile, label: str) -> Dict[str, Any]:
        if not upload or not upload.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{label} is required.",
            )

        mime_type = (upload.content_type or "").lower()
        if mime_type not in self.ALLOWED_VERIFICATION_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{label} must be a PDF, Word document (.doc/.docx), or image (JPG/PNG).",
            )

        data = await upload.read()
        await upload.close()

        if not data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{label} is empty.",
            )

        if len(data) > VERIFICATION_FILE_MAX_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"{label} exceeds the 10MB limit.",
            )

        extension = os.path.splitext(upload.filename)[1].lower()
        if not extension:
            extension = self.ALLOWED_VERIFICATION_MIME_TYPES.get(mime_type) or mimetypes.guess_extension(mime_type) or ""

        return {
            "bytes": data,
            "mime_type": mime_type,
            "extension": extension or ".bin",
            "filename": upload.filename,
        }

    def _upload_verification_document(
        self,
        *,
        user_id: str,
        submission_id: str,
        slug: str,
        payload: Dict[str, Any],
    ) -> str:
        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection error",
            )

        path = f"{user_id}/{submission_id}/{slug}{payload['extension']}"

        try:
            supabase.storage.from_(VERIFICATION_BUCKET_NAME).upload(
                path=path,
                file=payload["bytes"],
                file_options={
                    "content-type": payload["mime_type"],
                    "upsert": "false",
                },
            )
        except Exception as e:
            logger.error(f"Failed to upload verification document {path}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to upload verification documents.",
            )

        return path

    def _delete_storage_object(self, path: Optional[str]) -> None:
        if not path:
            return

        supabase = get_supabase_client()
        if not supabase:
            return

        try:
            supabase.storage.from_(VERIFICATION_BUCKET_NAME).remove([path])
        except Exception as e:
            logger.error(f"Failed to remove storage object {path}: {e}")

    def _send_review_email(self, email_method, *args) -> None:
        try:
            email_method(*args)
        except Exception as e:
            logger.error(f"Review email send failed: {e}")

    def _insert_user_row_for_signup(
        self,
        *,
        user_id: str,
        payload: RegisterRequest,
        age: int,
        signup_method: str,
        verification_status: str,
        personal_email: Optional[str] = None,
    ) -> None:
        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection error",
            )

        profile_data = {
            "id": user_id,
            "email": self._normalize_email(payload.email),
            "name": payload.name,
            "first_name": payload.first_name,
            "last_name": payload.last_name,
            "student_id": payload.student_id,
            "nationality": payload.nationality,
            "university": payload.university,
            "phone_number": payload.phone_number,
            "age": age,
            "date_of_birth": payload.date_of_birth,
            "account_type": "free",
            "logged_in": False,
            "verification_status": verification_status,
            "verification_submitted_at": datetime.now(timezone.utc).isoformat(),
            "signup_method": signup_method,
        }
        if personal_email:
            profile_data["personal_email"] = personal_email
            profile_data["personal_email_verified_at"] = datetime.now(timezone.utc).isoformat()

        try:
            supabase.table("users").insert(profile_data).execute()
        except Exception as e:
            err_msg = str(e).lower()
            if "23505" in err_msg or "duplicate" in err_msg or "unique" in err_msg:
                if "personal_email" in err_msg:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="This personal email is already linked to another account.",
                    )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An account with this email already exists.",
                )
            logger.error(f"Failed to insert user into public.users: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user profile. Please try again.",
            )

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
                "account_type": "free",
                "verification_status": "approved",
                "signup_method": "legacy_otp",
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
        """
        Forgot password: route OTP to the user's personal_email.

        The client may type either their university email or their personal
        email — we look up the row by either column. The OTP is ALWAYS sent
        to personal_email (university inboxes reject transactional mail).
        If the row has no personal_email yet, return a 409 so the client can
        route the user to the in-app lockout flow to add one first.
        """
        user = self._resolve_user_by_any_email(email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No account found with this email.",
            )

        personal_email = (user.get("personal_email") or "").strip().lower()
        if not personal_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "personal_email_required",
                    "message": "Please log in and add a personal email before resetting your password.",
                },
            )

        user_id = str(user["id"])
        otp_code = "".join(random.choices(string.digits, k=6))
        redis_key = f"sv:app:auth:forgot_otp:{user_id}"
        if not redis_manager.setex(redis_key, 300, otp_code):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate verification code",
            )

        try:
            email_service.send_otp_email(personal_email, otp_code, expiry_minutes=5)
        except Exception as e:
            redis_manager.delete(redis_key)
            logger.error(f"Failed to send forgot-password OTP to {personal_email}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send verification code",
            )

        # Masked echo so the client can show "sent to j***@gmail.com"
        local, _, domain = personal_email.partition("@")
        masked = f"{local[0]}{'*' * max(1, len(local) - 1)}@{domain}" if local else personal_email
        return {"message": "OTP sent", "sent_to": masked}

    async def forgot_password_verify_otp(self, email: str, code: str) -> Dict[str, Any]:
        """Verify OTP for forgot password and issue a temporary reset token."""
        user = self._resolve_user_by_any_email(email)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired or invalid")

        user_id = str(user["id"])
        redis_key = f"sv:app:auth:forgot_otp:{user_id}"
        stored_code = redis_manager.get(redis_key)

        if not stored_code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired or invalid")
        if stored_code != code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid access code")

        reset_token = str(uuid.uuid4())
        redis_manager.setex(f"sv:app:auth:reset_token:{user_id}", 600, reset_token)
        redis_manager.delete(redis_key)

        return {"reset_token": reset_token}

    async def forgot_password_reset(self, email: str, reset_token: str, new_password: str) -> Dict[str, Any]:
        """Use the temporary reset token to set a new password via Supabase Auth Admin API."""
        user = self._resolve_user_by_any_email(email)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        user_id = str(user["id"])
        token_key = f"sv:app:auth:reset_token:{user_id}"
        stored_token = redis_manager.get(token_key)

        if not stored_token or stored_token != reset_token:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")

        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database connection error")

        try:
            supabase.auth.admin.update_user_by_id(user_id, {"password": new_password})
            logger.info(f"Password reset successfully for user: {user_id}")
        except Exception as e:
            logger.error(f"Failed to reset password for user {user_id}: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to reset password")

        redis_manager.delete(token_key)
        return {"message": "Password reset successfully"}

    # ------------------------------------------------------------------
    # Signup personal-email OTP (step 2 of the new sign-up flow)
    # ------------------------------------------------------------------

    async def signup_send_personal_email_otp(self, personal_email: str) -> Dict[str, str]:
        """
        Send a 6-digit OTP to the personal email supplied at sign-up step 1.

        Rejects if the domain belongs to a known university (this is the
        personal-email input, not the university-email input) or if the
        address is already linked to a verified account.
        """
        normalized = self._normalize_email(personal_email)
        if self._domain_is_university(normalized):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please use a personal email, not your university email.",
            )

        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection error",
            )

        try:
            existing = (
                supabase.table("users")
                .select("id")
                .eq("personal_email", normalized)
                .limit(1)
                .execute()
            )
            if existing.data:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This email is already linked to another account.",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Personal email duplicate check failed: {e}")

        otp_code = "".join(random.choices(string.digits, k=6))
        redis_key = f"sv:app:auth:signup_otp:{normalized}"
        if not redis_manager.setex(redis_key, 300, otp_code):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate verification code",
            )

        try:
            email_service.send_otp_email(normalized, otp_code, expiry_minutes=5)
        except Exception as e:
            redis_manager.delete(redis_key)
            logger.error(f"Failed to send signup OTP to {normalized}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send verification code",
            )

        return {"message": "OTP sent"}

    async def signup_verify_personal_email_otp(self, personal_email: str, code: str) -> Dict[str, Any]:
        """Verify the signup OTP and issue a 15-minute signup token."""
        normalized = self._normalize_email(personal_email)
        redis_key = f"sv:app:auth:signup_otp:{normalized}"
        stored_code = redis_manager.get(redis_key)
        if not stored_code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired or invalid")
        if stored_code != code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid access code")

        supabase = get_supabase_client()
        if supabase:
            try:
                dup = (
                    supabase.table("users")
                    .select("id")
                    .eq("personal_email", normalized)
                    .limit(1)
                    .execute()
                )
                if dup.data:
                    redis_manager.delete(redis_key)
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="This email is already linked to another account.",
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Personal email re-check failed: {e}")

        signup_token = str(uuid.uuid4())
        redis_manager.setex(f"sv:app:auth:signup_token:{normalized}", 900, signup_token)
        redis_manager.delete(redis_key)
        return {"signup_token": signup_token, "personal_email": normalized}

    def _consume_signup_token(self, personal_email: str, signup_token: str) -> None:
        """Validate and delete a signup token. Raises 401 if invalid."""
        normalized = self._normalize_email(personal_email)
        token_key = f"sv:app:auth:signup_token:{normalized}"
        stored = redis_manager.get(token_key)
        if not stored or stored != signup_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Signup session expired. Please verify your email again.",
            )
        redis_manager.delete(token_key)

    # ------------------------------------------------------------------
    # Personal email add/verify (authenticated — used by lockout screen)
    # ------------------------------------------------------------------

    async def personal_email_send_otp(self, user_id: str, personal_email: str) -> Dict[str, str]:
        """
        Send an OTP to a personal email so a logged-in user can attach it to
        their account (powers the PersonalEmailRequiredScreen lockout).
        """
        normalized = self._normalize_email(personal_email)
        if self._domain_is_university(normalized):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please use a personal email, not your university email.",
            )

        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection error",
            )

        try:
            existing = (
                supabase.table("users")
                .select("id")
                .eq("personal_email", normalized)
                .neq("id", user_id)
                .limit(1)
                .execute()
            )
            if existing.data:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This email is already linked to another account.",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Personal email duplicate check failed: {e}")

        otp_code = "".join(random.choices(string.digits, k=6))
        # Key by user_id so an attacker can't target arbitrary inboxes by swapping
        # the personal_email; the OTP is always verified against the caller's id.
        redis_key = f"sv:app:auth:personal_email_otp:{user_id}"
        payload = f"{otp_code}|{normalized}"
        if not redis_manager.setex(redis_key, 300, payload):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate verification code",
            )

        try:
            email_service.send_otp_email(normalized, otp_code, expiry_minutes=5)
        except Exception as e:
            redis_manager.delete(redis_key)
            logger.error(f"Failed to send personal-email OTP to {normalized}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send verification code",
            )

        return {"message": "OTP sent"}

    async def personal_email_verify_otp(
        self, user_id: str, personal_email: str, code: str
    ) -> Dict[str, Any]:
        """Verify the personal-email OTP and persist it on public.users."""
        normalized = self._normalize_email(personal_email)
        redis_key = f"sv:app:auth:personal_email_otp:{user_id}"
        stored = redis_manager.get(redis_key)
        if not stored:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired or invalid")

        try:
            stored_code, _, stored_email = stored.partition("|")
        except Exception:
            stored_code, stored_email = stored, ""

        if stored_email != normalized:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email mismatch. Please request a new code.",
            )
        if stored_code != code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid access code")

        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection error",
            )

        try:
            dup = (
                supabase.table("users")
                .select("id")
                .eq("personal_email", normalized)
                .neq("id", user_id)
                .limit(1)
                .execute()
            )
            if dup.data:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This email is already linked to another account.",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Personal email re-check failed for user {user_id}: {e}")

        try:
            supabase.table("users").update({
                "personal_email": normalized,
                "personal_email_verified_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", user_id).execute()
        except Exception as e:
            err_msg = str(e).lower()
            if "23505" in err_msg or "duplicate" in err_msg or "unique" in err_msg:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This email is already linked to another account.",
                )
            logger.error(f"Failed to persist personal_email for user {user_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save personal email. Please try again.",
            )

        redis_manager.delete(redis_key)
        return {"personal_email": normalized, "message": "Personal email verified."}

    # ------------------------------------------------------------------
    # Manual Review Signup
    # ------------------------------------------------------------------

    async def manual_signup(
        self,
        *,
        email: str,
        personal_email: str,
        signup_token: str,
        first_name: str,
        last_name: str,
        nationality: Optional[str],
        university: Optional[str],
        phone_number: Optional[str],
        date_of_birth: str,
        password: str,
        student_id: Optional[str],
        enrollment_document: Optional[UploadFile],
        student_id_document: Optional[UploadFile],
    ) -> Dict[str, Any]:
        if enrollment_document is None and student_id_document is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please provide either an enrollment document or a student ID photo.",
            )

        normalized_email = self._normalize_email(email)
        normalized_personal_email = self._normalize_email(personal_email)

        # Verify the personal-email signup token (proves the personal inbox is
        # reachable) and consume it so the same token cannot be reused.
        self._consume_signup_token(normalized_personal_email, signup_token)

        if self._domain_is_university(normalized_personal_email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Personal email must not be a university email.",
            )

        canonical_university = self._lookup_verified_university(normalized_email)
        date_of_birth_iso, age = self._parse_date_of_birth(date_of_birth)

        register_request = RegisterRequest(
            email=normalized_email,
            name=f"{first_name} {last_name}",
            first_name=first_name,
            last_name=last_name,
            student_id=student_id,
            nationality=nationality,
            university=canonical_university,
            phone_number=phone_number,
            age=age,
            date_of_birth=date_of_birth_iso,
            password=password,
        )

        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database connection error")

        blacklist = supabase.table("user_blacklist").select("email").eq("email", normalized_email).execute()
        if blacklist.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "ACCOUNT_SUSPENDED",
                    "message": (
                        "Your account was suspended due to repeated rejections. "
                        "Please email support@studentverse.ae to rectify this."
                    ),
                    "verification_status": "suspended",
                },
            )

        existing = supabase.table("users").select(
            "id, verification_status"
        ).eq("email", normalized_email).execute()
        if existing.data:
            existing_status = existing.data[0].get("verification_status") or "approved"
            if existing_status == "suspended":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "ACCOUNT_SUSPENDED",
                        "message": (
                            "Your account was suspended due to repeated rejections. "
                            "Please email support@studentverse.ae to rectify this."
                        ),
                        "verification_status": "suspended",
                    },
                )
            if existing_status == "pending_review":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "ACCOUNT_PENDING_REVIEW",
                        "message": "Your account is already under review.",
                        "verification_status": "pending_review",
                    },
                )
            if existing_status == "rejected":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "ACCOUNT_REJECTED",
                        "message": "Your account was rejected. Please resubmit your documents instead.",
                        "verification_status": "rejected",
                    },
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists. Please use the login screen.",
            )

        personal_dup = (
            supabase.table("users")
            .select("id")
            .eq("personal_email", normalized_personal_email)
            .limit(1)
            .execute()
        )
        if personal_dup.data:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This personal email is already linked to another account.",
            )

        enrollment_payload = (
            await self._read_verification_file(enrollment_document, "Enrollment document")
            if enrollment_document is not None
            else None
        )
        student_id_payload = (
            await self._read_verification_file(student_id_document, "Student ID document")
            if student_id_document is not None
            else None
        )

        auth_user = None
        submission_id = None
        uploaded_paths: list[str] = []

        try:
            try:
                auth_response = supabase.auth.admin.create_user({
                    "email": normalized_email,
                    "password": password,
                    "email_confirm": True,
                    "user_metadata": {
                        "signup_method": "manual_review",
                    },
                })
                auth_user = getattr(auth_response, "user", None) or getattr(auth_response, "data", None)
                if not auth_user:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to create account. Please try again.",
                    )
                user_id = self._extract_auth_user_id(auth_user)
            except HTTPException:
                raise
            except Exception as create_err:
                err_msg = str(create_err).lower()
                if "already been registered" in err_msg or "already registered" in err_msg or "already exists" in err_msg:
                    # We already confirmed public.users has no row for this email above,
                    # so any auth.users record is an orphan from a prior failed attempt.
                    # Adopt it: reset password, reuse user_id, continue signup.
                    orphan_id = self._find_auth_user_id_by_email(supabase, normalized_email)
                    if not orphan_id:
                        logger.error(
                            f"Auth reports {normalized_email} exists but list_users could not locate it"
                        )
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail="An account with this email already exists. Please use the login screen or contact support.",
                        )
                    try:
                        supabase.auth.admin.update_user_by_id(
                            orphan_id,
                            {"password": password, "email_confirm": True},
                        )
                    except Exception as upd_err:
                        logger.error(f"Failed to adopt orphan auth user {orphan_id}: {upd_err}")
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to submit account for review. Please try again.",
                        )
                    logger.warning(
                        f"Adopted orphan auth.users record for {normalized_email} (id={orphan_id})"
                    )
                    auth_user = {"id": orphan_id, "email": normalized_email}
                    user_id = orphan_id
                else:
                    raise

            self._insert_user_row_for_signup(
                user_id=user_id,
                payload=register_request,
                age=age,
                signup_method="manual_review",
                verification_status="pending_review",
                personal_email=normalized_personal_email,
            )

            submission_insert = supabase.table("user_verification_submissions").insert({
                "user_id": user_id,
                "status": "pending_review",
            }).execute()
            if not submission_insert.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create verification submission.",
                )
            submission_id = submission_insert.data[0]["id"]

            submission_update: Dict[str, Any] = {}
            if enrollment_payload is not None:
                enrollment_path = self._upload_verification_document(
                    user_id=user_id,
                    submission_id=submission_id,
                    slug="enrollment",
                    payload=enrollment_payload,
                )
                uploaded_paths.append(enrollment_path)
                submission_update["enrollment_document_path"] = enrollment_path
                submission_update["enrollment_document_name"] = enrollment_payload["filename"]

            if student_id_payload is not None:
                student_id_path = self._upload_verification_document(
                    user_id=user_id,
                    submission_id=submission_id,
                    slug="student-id",
                    payload=student_id_payload,
                )
                uploaded_paths.append(student_id_path)
                submission_update["student_id_document_path"] = student_id_path
                submission_update["student_id_document_name"] = student_id_payload["filename"]

            if submission_update:
                supabase.table("user_verification_submissions").update(
                    submission_update
                ).eq("id", submission_id).execute()

            self._send_review_email(email_service.send_review_submission_email, normalized_email)

            return {
                "email": normalized_email,
                "verification_status": "pending_review",
                "message": "Your account is under review. We will email you once it is approved.",
            }
        except HTTPException:
            for path in uploaded_paths:
                self._delete_storage_object(path)
            if submission_id:
                try:
                    supabase.table("user_verification_submissions").delete().eq("id", submission_id).execute()
                except Exception as e:
                    logger.error(f"Failed to rollback verification submission {submission_id}: {e}")
            if auth_user:
                try:
                    rollback_user_id = getattr(auth_user, "id", None) or (
                        auth_user.get("id") if isinstance(auth_user, dict) else None
                    )
                    if rollback_user_id:
                        supabase.table("users").delete().eq("id", str(rollback_user_id)).execute()
                        supabase.auth.admin.delete_user(str(rollback_user_id))
                except Exception as e:
                    logger.error(f"Failed to rollback manual signup for {normalized_email}: {e}")
            raise
        except Exception as e:
            logger.error(f"Manual signup failed for {normalized_email}: {e}", exc_info=True)
            for path in uploaded_paths:
                self._delete_storage_object(path)
            if submission_id:
                try:
                    supabase.table("user_verification_submissions").delete().eq("id", submission_id).execute()
                except Exception:
                    pass
            if auth_user:
                try:
                    rollback_user_id = getattr(auth_user, "id", None) or (
                        auth_user.get("id") if isinstance(auth_user, dict) else None
                    )
                    if rollback_user_id:
                        supabase.table("users").delete().eq("id", str(rollback_user_id)).execute()
                        supabase.auth.admin.delete_user(str(rollback_user_id))
                except Exception:
                    pass
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to submit account for review. Please try again.",
            )

    async def manual_signup_resubmit(
        self,
        *,
        email: str,
        password: str,
        enrollment_document: Optional[UploadFile],
        student_id_document: Optional[UploadFile],
    ) -> Dict[str, Any]:
        if enrollment_document is None and student_id_document is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please provide either an enrollment document or a student ID photo.",
            )

        normalized_email = self._normalize_email(email)
        enrollment_payload = (
            await self._read_verification_file(enrollment_document, "Enrollment document")
            if enrollment_document is not None
            else None
        )
        student_id_payload = (
            await self._read_verification_file(student_id_document, "Student ID document")
            if student_id_document is not None
            else None
        )

        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database connection error")

        user_lookup = supabase.table("users").select(
            "id, email, verification_status"
        ).eq("email", normalized_email).execute()
        if not user_lookup.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No account found with this email.")

        user = user_lookup.data[0]
        if user.get("verification_status") != "rejected":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only rejected accounts can resubmit documents.",
            )

        auth_client = create_fresh_supabase_client()
        if not auth_client:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database connection error")

        try:
            auth_response = auth_client.auth.sign_in_with_password({"email": normalized_email, "password": password})
        except Exception as e:
            logger.error(f"Manual resubmission password validation failed: {e}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

        if not auth_response or not auth_response.user or not auth_response.session:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

        user_id = str(auth_response.user.id)
        access_token = auth_response.session.access_token

        submission_id = None
        uploaded_paths: list[str] = []

        try:
            submission_insert = supabase.table("user_verification_submissions").insert({
                "user_id": user_id,
                "status": "pending_review",
            }).execute()
            if not submission_insert.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create verification submission.",
                )
            submission_id = submission_insert.data[0]["id"]

            submission_update: Dict[str, Any] = {}
            if enrollment_payload is not None:
                enrollment_path = self._upload_verification_document(
                    user_id=user_id,
                    submission_id=submission_id,
                    slug="enrollment",
                    payload=enrollment_payload,
                )
                uploaded_paths.append(enrollment_path)
                submission_update["enrollment_document_path"] = enrollment_path
                submission_update["enrollment_document_name"] = enrollment_payload["filename"]

            if student_id_payload is not None:
                student_id_path = self._upload_verification_document(
                    user_id=user_id,
                    submission_id=submission_id,
                    slug="student-id",
                    payload=student_id_payload,
                )
                uploaded_paths.append(student_id_path)
                submission_update["student_id_document_path"] = student_id_path
                submission_update["student_id_document_name"] = student_id_payload["filename"]

            if submission_update:
                supabase.table("user_verification_submissions").update(
                    submission_update
                ).eq("id", submission_id).execute()

            supabase.table("users").update({
                "verification_status": "pending_review",
                "verification_submitted_at": datetime.now(timezone.utc).isoformat(),
                "verification_reviewed_at": None,
                "verification_reviewed_by": None,
                "verification_rejection_reason": None,
            }).eq("id", user_id).execute()

            self._send_review_email(email_service.send_review_resubmitted_email, normalized_email)

            return {
                "email": normalized_email,
                "verification_status": "pending_review",
                "message": "Your updated documents are under review.",
            }
        except HTTPException:
            for path in uploaded_paths:
                self._delete_storage_object(path)
            if submission_id:
                try:
                    supabase.table("user_verification_submissions").delete().eq("id", submission_id).execute()
                except Exception as e:
                    logger.error(f"Failed to rollback resubmission {submission_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Manual resubmission failed for {normalized_email}: {e}", exc_info=True)
            for path in uploaded_paths:
                self._delete_storage_object(path)
            if submission_id:
                try:
                    supabase.table("user_verification_submissions").delete().eq("id", submission_id).execute()
                except Exception:
                    pass
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to resubmit documents. Please try again.",
            )
        finally:
            try:
                supabase.auth.admin.sign_out(access_token)
            except Exception as e:
                logger.error(f"Failed to invalidate temporary resubmission token: {e}")

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
            user_check = supabase.table("users").select(
                "id, email, verification_status, verification_rejection_reason"
            ).eq("email", email).execute()
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
        user_row = user_check.data[0]
        verification_status = user_row.get("verification_status") or "approved"

        if verification_status != "approved":
            try:
                supabase.auth.admin.sign_out(access_token)
            except Exception as e:
                logger.error(f"Failed to invalidate blocked login token for {email}: {e}")

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=self._build_review_error_detail(user_row),
            )

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

    async def get_profile(self, user_id: str) -> Dict[str, Any]:
        """Fetch a single public.users row by id."""
        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Database connection error")

        try:
            result = supabase.table("users").select("*").eq("id", user_id).single().execute()
        except Exception as e:
            logger.error(f"Get profile error: {e}")
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to fetch profile")

        if not result.data:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
        return result.data

    async def upload_profile_image(self, user_id: str, upload: UploadFile) -> Dict[str, Any]:
        """
        Upload a profile picture to the public profile-images bucket and update
        public.users.avatar_url with the resolved CDN URL.

        Each upload writes to a unique timestamped path so old URLs naturally
        cache-bust on the frontend.
        """
        if not upload or not upload.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Profile image is required.",
            )

        mime_type = (upload.content_type or "").lower()
        if mime_type not in ALLOWED_PROFILE_IMAGE_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Profile image must be a JPG, PNG, or WEBP file.",
            )

        data = await upload.read()
        await upload.close()

        if not data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Profile image is empty.",
            )

        if len(data) > PROFILE_IMAGE_MAX_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Profile image exceeds the 5MB limit.",
            )

        extension = os.path.splitext(upload.filename)[1].lower()
        if not extension:
            extension = ALLOWED_PROFILE_IMAGE_MIME_TYPES.get(mime_type) or ".jpg"

        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection error",
            )

        timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        path = f"{user_id}/pfp-{timestamp_ms}{extension}"

        try:
            supabase.storage.from_(PROFILE_IMAGE_BUCKET_NAME).upload(
                path=path,
                file=data,
                file_options={
                    "content-type": mime_type,
                    "upsert": "false",
                },
            )
        except Exception as e:
            logger.error(f"Failed to upload profile image {path}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to upload profile image.",
            )

        try:
            public_url = supabase.storage.from_(PROFILE_IMAGE_BUCKET_NAME).get_public_url(path)
        except Exception as e:
            logger.error(f"Failed to resolve public URL for {path}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to resolve profile image URL.",
            )

        avatar_url = (public_url or "").strip().rstrip("?")

        try:
            supabase.table("users").update({"avatar_url": avatar_url}).eq("id", user_id).execute()
        except Exception as e:
            logger.error(f"Failed to persist avatar_url for user {user_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Profile image uploaded but failed to save on profile.",
            )

        return {"avatar_url": avatar_url, "storage_path": path}

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
            except Exception as e:
                logger.error(f"Failed to clean up Redis auth keys for {email}: {e}")
        try:
            redis_manager.delete(f"sv:app:auth:forgot_otp:{user_id}")
            redis_manager.delete(f"sv:app:auth:reset_token:{user_id}")
            redis_manager.delete(f"sv:app:auth:personal_email_otp:{user_id}")
        except Exception as e:
            logger.error(f"Failed to clean up Redis auth keys for user {user_id}: {e}")

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

    # ------------------------------------------------------------------
    # Microsoft OAuth Verification (sign-up + forgot-password)
    # ------------------------------------------------------------------

    async def list_verified_institutions(self) -> list:
        """Return list of active verified universities for frontend dropdown."""
        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection error"
            )

        try:
            result = (
                supabase.table("university_domains")
                .select("university_name, domain")
                .eq("is_active", True)
                .order("university_name")
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to fetch institutions: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to load institutions"
            )

    def _validate_azure_token(self, access_token: str):
        """
        Validate a Supabase Azure OAuth token and return the authenticated user.

        Returns (auth_user, email, domain, university_name) tuple.

        Raises HTTPException on any validation failure.
        """
        # 1. Validate token with a fresh client
        fresh = create_fresh_supabase_client()
        if not fresh:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection error"
            )

        try:
            auth_response = fresh.auth.get_user(access_token)
        except Exception as e:
            logger.error(f"Azure token validation failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired authentication session"
            )

        if not auth_response or not auth_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired authentication session"
            )

        auth_user = auth_response.user

        # 2. Confirm provider is Azure
        provider = None
        if auth_user.app_metadata:
            provider = auth_user.app_metadata.get("provider")
        # Also check identities array as fallback
        if not provider and auth_user.identities:
            for identity in auth_user.identities:
                if hasattr(identity, 'provider'):
                    provider = identity.provider
                    break
                elif isinstance(identity, dict):
                    provider = identity.get("provider")
                    break

        if provider != "azure":
            logger.warning(f"Non-Azure provider attempted: {provider}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid authentication provider. Please sign in with your Microsoft university account."
            )

        # 3. Extract and normalize email (from Supabase, NOT from request body)
        email = auth_user.email
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No email found in authentication session"
            )

        email = email.lower().strip()

        try:
            domain = email.split("@")[1]
        except IndexError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email format"
            )

        # 4. Whitelist domain check (BLOCKING)
        university_name = self._lookup_verified_university(email)

        return auth_user, email, domain, university_name

    async def verify_microsoft_signup(self, access_token: str) -> Dict[str, Any]:
        """
        Verify Microsoft Azure OAuth session for new user sign-up.

        This replaces verify_otp() as the identity gate for sign-up:
        1. Validates Azure OAuth token
        2. Confirms provider is Azure
        3. Extracts email from token (NOT from request body)
        4. Validates email domain against university whitelist (BLOCKING)
        5. Rejects if account already exists
        6. Creates Supabase Auth user + public.users row
        7. Returns access token for registration completion
        """
        auth_user, email, domain, university_name = self._validate_azure_token(access_token)

        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection error"
            )

        # 5. Reject if account already exists in public.users
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

        # 6. Create Supabase Auth user + public.users row
        #    (same pattern as verify_otp)
        auth_client = create_fresh_supabase_client()
        if not auth_client:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection error"
            )

        temp_password = secrets.token_urlsafe(32)
        try:
            signup_response = auth_client.auth.sign_up({"email": email, "password": temp_password})
        except Exception as e:
            logger.error(f"Supabase sign_up failed for Microsoft user: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create account. Please try again."
            )

        if not signup_response or not signup_response.user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create account"
            )

        if not signup_response.session or not signup_response.session.access_token:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Account created but no session returned. Ensure email confirmation is disabled in Supabase."
            )

        user_id = str(signup_response.user.id)
        new_access_token = signup_response.session.access_token

        # Insert into public.users
        try:
            supabase.table("users").insert({
                "id": user_id,
                "email": email,
                "account_type": "free",
                "verification_status": "approved",
                "signup_method": "azure_oauth",
            }).execute()
            logger.info(f"Created user in public.users via Microsoft OAuth: {email}")
        except Exception as e:
            logger.error(f"Failed to insert user into public.users: {e}")
            # Roll back the Supabase Auth user so it's not orphaned
            try:
                supabase.auth.admin.delete_user(user_id)
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user profile. Please try again."
            )

        logger.info(f"Microsoft OAuth signup verified: {email} ({university_name})")

        return {
            "status": "success",
            "message": "Microsoft verification successful. Please complete your registration.",
            "email": email,
            "university_name": university_name,
            "is_new_user": True,
            "access_token": new_access_token,
            "token_type": "bearer",
            "user": {"id": user_id, "email": email}
        }

    async def verify_microsoft_recovery(self, access_token: str) -> Dict[str, Any]:
        """
        Verify Microsoft Azure OAuth session for password recovery.

        1. Validates Azure OAuth token
        2. Confirms provider is Azure
        3. Extracts email from token
        4. Validates email domain against university whitelist
        5. Confirms completed account exists in public.users
        6. Issues short-lived reset token (same pattern as forgot_password_verify_otp)
        """
        auth_user, email, domain, university_name = self._validate_azure_token(access_token)

        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection error"
            )

        # 5. Confirm completed account exists
        try:
            user_check = supabase.table("users").select("id").eq("email", email).execute()
            if not user_check.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No account found with this email."
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"User lookup failed during Microsoft recovery: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error during recovery verification"
            )

        # 6. Issue short-lived reset token (same pattern as forgot_password_verify_otp)
        user_id = str(user_check.data[0]["id"])
        reset_token = str(uuid.uuid4())
        redis_manager.setex(f"sv:app:auth:reset_token:{user_id}", 600, reset_token)

        logger.info(f"Microsoft OAuth recovery verified: {email}")

        return {
            "email": email,
            "reset_token": reset_token
        }

    # ------------------------------------------------------------------
    # Internal admin review actions
    # ------------------------------------------------------------------

    async def approve_verification_submission(self, submission_id: str, reviewer: str) -> Dict[str, Any]:
        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection error",
            )

        submission_result = supabase.table("user_verification_submissions").select(
            "id, user_id, status, users!inner(email)"
        ).eq("id", submission_id).execute()

        if not submission_result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification submission not found.")

        submission = submission_result.data[0]
        if submission.get("status") != "pending_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This verification submission has already been reviewed.",
            )

        reviewed_at = datetime.now(timezone.utc).isoformat()
        user_id = submission["user_id"]
        related_user = submission.get("users")
        user_email = related_user[0]["email"] if isinstance(related_user, list) else related_user["email"]

        supabase.table("user_verification_submissions").update({
            "status": "approved",
            "reviewed_by": reviewer,
            "reviewed_at": reviewed_at,
            "rejection_reason": None,
        }).eq("id", submission_id).execute()

        supabase.table("users").update({
            "verification_status": "approved",
            "verification_reviewed_at": reviewed_at,
            "verification_reviewed_by": reviewer,
            "verification_rejection_reason": None,
        }).eq("id", user_id).execute()

        self._send_review_email(email_service.send_review_approved_email, user_email)

        return {
            "submission_id": submission_id,
            "user_id": user_id,
            "verification_status": "approved",
        }

    async def reject_verification_submission(self, submission_id: str, reviewer: str, reason: str) -> Dict[str, Any]:
        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection error",
            )

        submission_result = supabase.table("user_verification_submissions").select(
            "id, user_id, status, users!inner(email)"
        ).eq("id", submission_id).execute()

        if not submission_result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification submission not found.")

        submission = submission_result.data[0]
        if submission.get("status") != "pending_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This verification submission has already been reviewed.",
            )

        reviewed_at = datetime.now(timezone.utc).isoformat()
        user_id = submission["user_id"]
        related_user = submission.get("users")
        user_email = related_user[0]["email"] if isinstance(related_user, list) else related_user["email"]

        supabase.table("user_verification_submissions").update({
            "status": "rejected",
            "reviewed_by": reviewer,
            "reviewed_at": reviewed_at,
            "rejection_reason": reason,
        }).eq("id", submission_id).execute()

        supabase.table("users").update({
            "verification_status": "rejected",
            "verification_reviewed_at": reviewed_at,
            "verification_reviewed_by": reviewer,
            "verification_rejection_reason": reason,
        }).eq("id", user_id).execute()

        self._send_review_email(email_service.send_review_rejected_email, user_email, reason)

        return {
            "submission_id": submission_id,
            "user_id": user_id,
            "verification_status": "rejected",
            "review_reason": reason,
        }


# Singleton instance
auth_service = AuthService()
