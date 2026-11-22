"""
Authentication Service

Auth flow:
  SIGN UP:  send_otp -> verify_otp -> complete_registration
  LOGIN:    login (email + password)

Self-managed Auth (Azure PostgreSQL + Azure Blob Storage + Custom JWT).
Single-device enforcement uses device_id binding.
"""
import secrets
import random
import string
import logging
import uuid
import os
import mimetypes
import re
import json
import httpx
from io import BytesIO
from datetime import date, datetime, timezone
from typing import Optional, Dict, Any, List
from fastapi import HTTPException, status, UploadFile
from pydantic import ValidationError as PydanticValidationError
from passlib.hash import bcrypt as bcrypt_hasher

from app.core.database import fetch_one, fetch_all, execute, fetch_val
from app.core.storage import upload_blob, delete_blob, get_blob_url
from app.core.jwt_utils import create_access_token, decode_access_token
from app.core.redis import redis_manager
from app.core.email import email_service
from app.core.activity import log_activity_event, mark_login, mark_signup_versions
from app.modules.auth.schemas import RegisterRequest, ProfileUpdateRequest, UserStats
from app.modules.notifications.service import notification_service

logger = logging.getLogger(__name__)

VERIFICATION_BUCKET_NAME = os.getenv("VERIFICATION_BUCKET_NAME", "user-verification-documents")
VERIFICATION_FILE_MAX_BYTES = int(os.getenv("VERIFICATION_FILE_MAX_BYTES", "10485760"))
PROFILE_IMAGE_BUCKET_NAME = os.getenv("PROFILE_IMAGE_BUCKET_NAME", "user-profile-images")
PROFILE_IMAGE_MAX_BYTES = int(os.getenv("PROFILE_IMAGE_MAX_BYTES", "5242880"))
AI_SIGNUP_URL = os.getenv(
    "AI_SIGNUP_URL", "https://sv-orbit-ai-signup-production.up.railway.app"
).strip().rstrip("/")
AI_UNIVERSITY_ALIASES = {
    "university of wollongong in dubai": ("uowd", "wollongong"),
    "american university in dubai": ("aud",),
    "american university of sharjah": ("aus",),
    "university of birmingham dubai": ("uob dubai", "birmingham"),
    "heriot watt university dubai": ("heriot watt", "hwu"),
}
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

    def _find_auth_user_id_by_email(self, email: str) -> Optional[str]:
        target = email.strip().lower()
        row = fetch_one("SELECT id FROM users WHERE email = %s", (target,))
        return str(row["id"]) if row else None

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
        normalized = self._normalize_email(email)
        try:
            return fetch_one(
                "SELECT id, email, personal_email, password_hash FROM users WHERE email = %s OR personal_email = %s LIMIT 1",
                (normalized, normalized)
            )
        except Exception as e:
            logger.error(f"User resolve by any email failed for {normalized}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error",
            )

    def _domain_is_university(self, email: str) -> bool:
        try:
            domain = self._normalize_email(email).split("@", 1)[1]
        except IndexError:
            return False
        try:
            row = fetch_one("SELECT domain FROM university_domains WHERE domain = %s AND is_active = true LIMIT 1", (domain,))
            return bool(row)
        except Exception as e:
            logger.error(f"Domain lookup failed for {domain}: {e}")
            return False

    def _lookup_verified_university(self, email: str) -> str:
        normalized_email = self._normalize_email(email)
        try:
            domain = normalized_email.split("@", 1)[1]
        except IndexError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email format")

        try:
            row = fetch_one("SELECT university_name FROM university_domains WHERE domain = %s AND is_active = true LIMIT 1", (domain,))
        except Exception as e:
            logger.error(f"University domain lookup error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to verify university domain",
            )

        if not row:
            logger.warning(f"Unsupported university domain: {domain} (email: {normalized_email})")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Your university is not supported yet. Only verified UAE university email domains are accepted.",
            )

        return row["university_name"]

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

    @staticmethod
    def _normalize_identity_text(value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", (value or "").lower()))

    @classmethod
    def _first_name_identity_matches(cls, expected: str, document: str) -> bool:
        expected_parts = cls._normalize_identity_text(expected).split()
        document_parts = cls._normalize_identity_text(document).split()
        return bool(expected_parts and document_parts and expected_parts[0] == document_parts[0])

    @classmethod
    def _name_identity_matches(cls, expected: str, document: str) -> bool:
        expected_parts = cls._normalize_identity_text(expected).split()
        document_parts = cls._normalize_identity_text(document).split()
        if len(expected_parts) < 2 or len(document_parts) < 2:
            return False
        if expected_parts[0] != document_parts[0]:
            return False

        def family_suffixes(parts: list[str]) -> set[str]:
            return {
                "".join(parts[-size:])
                for size in range(1, min(3, len(parts) - 1) + 1)
            }

        return bool(family_suffixes(expected_parts) & family_suffixes(document_parts))

    @classmethod
    def _university_identity_matches(cls, expected: str, document: str) -> bool:
        expected_text = cls._normalize_identity_text(expected)
        document_text = cls._normalize_identity_text(document)
        if not expected_text or not document_text:
            return False
        if expected_text in document_text or document_text in expected_text:
            return True

        for canonical, aliases in AI_UNIVERSITY_ALIASES.items():
            candidates = (canonical, *aliases)
            normalized = tuple(cls._normalize_identity_text(value) for value in candidates)
            if any(value in expected_text for value in normalized) and any(
                value in document_text for value in normalized
            ):
                return True

        distinctive_words = {
            word
            for word in expected_text.split()
            if len(word) > 5
            and word not in {"university", "college", "institute", "dubai", "sharjah"}
        }
        return any(word in document_text.split() for word in distinctive_words)

    async def _verify_automated_signup(
        self,
        *,
        enrollment_payload: Dict[str, Any],
        student_id_payload: Dict[str, Any],
        first_name: str,
        last_name: str,
        university: str,
    ) -> Dict[str, Any]:
        files = {
            "student_id": (
                student_id_payload["filename"],
                student_id_payload["bytes"],
                student_id_payload["mime_type"],
            ),
            "university_letter": (
                enrollment_payload["filename"],
                enrollment_payload["bytes"],
                enrollment_payload["mime_type"],
            ),
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(f"{AI_SIGNUP_URL}/verify", files=files)
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "AI_VERIFICATION_UNAVAILABLE",
                    "message": "Automated verification is temporarily unavailable. Please try again or use manual verification.",
                },
            ) from None

        if response.status_code == 502 or response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "AI_VERIFICATION_FAILED",
                    "message": "Student documents could not be validated. Please upload a valid student ID and enrollment document.",
                },
            )

        result = response.json()
        if result.get("approved") is not True:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "AI_VERIFICATION_FAILED",
                    "message": "Student documents could not be validated. Please upload a valid student ID and enrollment document.",
                },
            )
        return result

    def _upload_verification_document(
        self,
        *,
        user_id: str,
        submission_id: str,
        slug: str,
        payload: Dict[str, Any],
    ) -> str:
        path = f"{user_id}/{submission_id}/{slug}{payload['extension']}"
        try:
            upload_blob(
                container_name=VERIFICATION_BUCKET_NAME,
                blob_path=path,
                data=payload["bytes"],
                content_type=payload["mime_type"],
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
        try:
            delete_blob(container_name=VERIFICATION_BUCKET_NAME, blob_path=path)
        except Exception as e:
            logger.error(f"Failed to remove storage object {path}: {e}")

    def _send_review_email(self, email_method, *args) -> None:
        try:
            email_method(*args)
        except Exception as e:
            logger.error(f"Review email send failed: {e}")

    async def _send_review_push(self, user_id: str, approved: bool) -> None:
        title = "WELCOME TO THE SV FAMILY!" if approved else "Application update needed"
        body = (
            "You’re officially verified. Tap in and start claiming the student deals you were waiting for."
            if approved
            else "Your student application needs a quick fix. Open StudentVerse to see what to resubmit."
        )
        try:
            await notification_service.send_campaign(
                title=title,
                body=body,
                actor="verification-review",
                user_ids=[str(user_id)],
                data={"route": "/auth/review-status", "status": "approved" if approved else "rejected"},
            )
        except Exception as e:
            logger.error(f"Review push send failed for user {user_id}: {e}")

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
        if payload.password:
            profile_data["password_hash"] = bcrypt_hasher.hash(payload.password)
        if verification_status == "approved":
            profile_data["verification_reviewed_at"] = datetime.now(timezone.utc).isoformat()
            profile_data["verification_reviewed_by"] = "automated_ai"
        if personal_email:
            profile_data["personal_email"] = personal_email
            profile_data["personal_email_verified_at"] = datetime.now(timezone.utc).isoformat()

        cols = list(profile_data.keys())
        col_names = ", ".join(cols)
        placeholders = ", ".join(["%s"] * len(cols))
        try:
            execute(f"INSERT INTO users ({col_names}) VALUES ({placeholders})", tuple(profile_data.values()))
        except Exception as e:
            err_msg = str(e).lower()
            if "duplicate" in err_msg or "unique" in err_msg or "23505" in err_msg:
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

        try:
            row = fetch_one("SELECT domain FROM university_domains WHERE domain = %s", (domain,))
            if not row:
                logger.warning(f"Domain {domain} not in university whitelist")
        except Exception as e:
            logger.error(f"Domain whitelist query error: {e}")

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

        try:
            email_service.send_otp_email(email, otp_code, expiry_minutes=5)
        except Exception as e:
            redis_manager.delete(redis_key)
            logger.error(f"Failed to send OTP email: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to send verification code")

        return {"message": "OTP sent"}

    def _get_otp_attempts_key(self, email: str) -> str:
        return f"sv:app:auth:otp_attempts:{email}"

    def _get_otp_lockout_key(self, email: str) -> str:
        return f"sv:app:auth:otp_lockout:{email}"

    async def _check_otp_rate_limit(self, email: str) -> None:
        lockout_key = self._get_otp_lockout_key(email)
        lockout_ttl = redis_manager.get(lockout_key)
        if lockout_ttl:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed attempts. Try again later."
            )

    async def _record_failed_otp_attempt(self, email: str) -> None:
        attempts_key = self._get_otp_attempts_key(email)
        current_attempts = redis_manager.get(attempts_key)
        MAX_ATTEMPTS = 5
        LOCKOUT_DURATION = 900

        if current_attempts is None:
            redis_manager.setex(attempts_key, 300, "1")
            current_attempts = 1
        else:
            new_attempts = int(current_attempts) + 1
            redis_manager.setex(attempts_key, 300, str(new_attempts))
            current_attempts = new_attempts

        if current_attempts >= MAX_ATTEMPTS:
            lockout_key = self._get_otp_lockout_key(email)
            redis_manager.setex(lockout_key, LOCKOUT_DURATION, "1")
            logger.warning(f"OTP lockout triggered for email {email} after {current_attempts} failed attempts")
            otp_key = f"sv:app:auth:otp:{email}"
            redis_manager.delete(otp_key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed attempts. Locked out for {LOCKOUT_DURATION // 60} minutes."
            )

    async def _clear_otp_attempts(self, email: str) -> None:
        attempts_key = self._get_otp_attempts_key(email)
        lockout_key = self._get_otp_lockout_key(email)
        redis_manager.delete(attempts_key)
        redis_manager.delete(lockout_key)

    async def verify_otp(
        self,
        email: str,
        code: str,
        device_id: str = "",
        *,
        app_version: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Verify OTP for NEW user sign-up only."""
        redis_key = f"sv:app:auth:otp:{email}"
        await self._check_otp_rate_limit(email)

        stored_code = redis_manager.get(redis_key)
        if not stored_code:
            await self._record_failed_otp_attempt(email)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired or invalid")
        if stored_code != code:
            await self._record_failed_otp_attempt(email)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid access code")

        await self._clear_otp_attempts(email)

        existing = fetch_one("SELECT id FROM users WHERE email = %s", (email,))
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists. Please use the login screen."
            )

        user_id = str(uuid.uuid4())
        access_token = create_access_token(user_id, email)

        try:
            execute(
                "INSERT INTO users (id, email, account_type, verification_status, signup_method) VALUES (%s, %s, 'free', 'approved', 'legacy_otp')",
                (user_id, email)
            )
            logger.info(f"Created user in public.users: {email}")
        except Exception as e:
            logger.error(f"Failed to insert user into public.users: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create user profile. Please try again.")

        redis_manager.delete(redis_key)
        mark_signup_versions(user_id, app_version=app_version, platform=platform)
        mark_login(user_id, app_version=app_version, platform=platform)

        return {
            "status": "success",
            "message": "OTP verified. Please complete your registration.",
            "access_token": access_token,
            "token_type": "bearer",
            "is_new_user": True,
            "user": {"id": user_id, "email": email}
        }

    async def forgot_password_send_otp(self, email: str) -> Dict[str, str]:
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

        local, _, domain = personal_email.partition("@")
        masked = f"{local[0]}{'*' * max(1, len(local) - 1)}@{domain}" if local else personal_email
        return {"message": "OTP sent", "sent_to": masked}

    async def forgot_password_verify_otp(self, email: str, code: str) -> Dict[str, Any]:
        user = self._resolve_user_by_any_email(email)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired or invalid")

        user_id = str(user["id"])
        redis_key = f"sv:app:auth:forgot_otp:{user_id}"

        await self._check_otp_rate_limit(email)
        stored_code = redis_manager.get(redis_key)

        if not stored_code:
            await self._record_failed_otp_attempt(email)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired or invalid")
        if stored_code != code:
            await self._record_failed_otp_attempt(email)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid access code")

        await self._clear_otp_attempts(email)
        reset_token = str(uuid.uuid4())
        redis_manager.setex(f"sv:app:auth:reset_token:{user_id}", 600, reset_token)
        redis_manager.delete(redis_key)

        return {"reset_token": reset_token}

    async def forgot_password_reset(self, email: str, reset_token: str, new_password: str) -> Dict[str, Any]:
        user = self._resolve_user_by_any_email(email)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        user_id = str(user["id"])
        token_key = f"sv:app:auth:reset_token:{user_id}"
        stored_token = redis_manager.get(token_key)

        if not stored_token or stored_token != reset_token:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")

        try:
            pw_hash = bcrypt_hasher.hash(new_password)
            execute("UPDATE users SET password_hash = %s WHERE id = %s", (pw_hash, user_id))
            logger.info(f"Password reset successfully for user: {user_id}")
        except Exception as e:
            logger.error(f"Failed to reset password for user {user_id}: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to reset password")

        redis_manager.delete(token_key)
        return {"message": "Password reset successfully"}

    async def signup_send_personal_email_otp(self, personal_email: str) -> Dict[str, str]:
        normalized = self._normalize_email(personal_email)
        if self._domain_is_university(normalized):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please use a personal email, not your university email.",
            )

        existing = fetch_one("SELECT id FROM users WHERE personal_email = %s LIMIT 1", (normalized,))
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This email is already linked to another account.",
            )

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
        normalized = self._normalize_email(personal_email)
        redis_key = f"sv:app:auth:signup_otp:{normalized}"
        await self._check_otp_rate_limit(normalized)

        stored_code = redis_manager.get(redis_key)
        if not stored_code:
            await self._record_failed_otp_attempt(normalized)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired or invalid")
        if stored_code != code:
            await self._record_failed_otp_attempt(normalized)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid access code")

        await self._clear_otp_attempts(normalized)

        dup = fetch_one("SELECT id FROM users WHERE personal_email = %s LIMIT 1", (normalized,))
        if dup:
            redis_manager.delete(redis_key)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This email is already linked to another account.",
            )

        signup_token = str(uuid.uuid4())
        redis_manager.setex(f"sv:app:auth:signup_token:{normalized}", 900, signup_token)
        redis_manager.delete(redis_key)
        return {"signup_token": signup_token, "personal_email": normalized}

    def _consume_signup_token(self, personal_email: str, signup_token: str) -> None:
        normalized = self._normalize_email(personal_email)
        token_key = f"sv:app:auth:signup_token:{normalized}"
        stored = redis_manager.get(token_key)
        if not stored or stored != signup_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Signup session expired. Please verify your email again.",
            )
        redis_manager.delete(token_key)

    async def personal_email_send_otp(self, user_id: str, personal_email: str) -> Dict[str, str]:
        normalized = self._normalize_email(personal_email)
        if self._domain_is_university(normalized):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please use a personal email, not your university email.",
            )

        existing = fetch_one("SELECT id FROM users WHERE personal_email = %s AND id != %s LIMIT 1", (normalized, user_id))
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This email is already linked to another account.",
            )

        otp_code = "".join(random.choices(string.digits, k=6))
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
        normalized = self._normalize_email(personal_email)
        redis_key = f"sv:app:auth:personal_email_otp:{user_id}"
        await self._check_otp_rate_limit(normalized)

        stored = redis_manager.get(redis_key)
        if not stored:
            await self._record_failed_otp_attempt(normalized)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired or invalid")

        try:
            stored_code, _, stored_email = stored.partition("|")
        except Exception:
            stored_code, stored_email = stored, ""

        if stored_email != normalized:
            await self._record_failed_otp_attempt(normalized)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email mismatch. Please request a new code.",
            )
        if stored_code != code:
            await self._record_failed_otp_attempt(normalized)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid access code")

        await self._clear_otp_attempts(normalized)

        dup = fetch_one("SELECT id FROM users WHERE personal_email = %s AND id != %s LIMIT 1", (normalized, user_id))
        if dup:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This email is already linked to another account.",
            )

        try:
            execute(
                "UPDATE users SET personal_email = %s, personal_email_verified_at = %s WHERE id = %s",
                (normalized, datetime.now(timezone.utc).isoformat(), user_id)
            )
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

    async def get_manual_signup_status(self, email: str) -> Dict[str, Any]:
        normalized_email = self._normalize_email(email)
        user = fetch_one(
            "SELECT email, verification_status, verification_rejection_reason FROM users WHERE email = %s OR personal_email = %s LIMIT 1",
            (normalized_email, normalized_email)
        )
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No application found with this email.")

        verification_status = user.get("verification_status") or "pending_review"
        reason = user.get("verification_rejection_reason")
        messages = {
            "pending_review": "Your application is currently under review by our team.",
            "approved": "Your account has been verified. You can now log in.",
            "rejected": "Your application could not be verified. Please review the reason and resubmit.",
            "suspended": "Your account was suspended due to repeated rejections. Please contact support.",
        }
        return {
            "email": user.get("email") or normalized_email,
            "verification_status": verification_status,
            "message": messages.get(verification_status, messages["pending_review"]),
            "review_reason": reason,
        }

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
        automated_verification: bool = False,
        app_version: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> Dict[str, Any]:
        if automated_verification and (enrollment_document is None or student_id_document is None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Automated verification requires both an enrollment document and a student ID photo.",
            )
        if enrollment_document is None and student_id_document is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please provide either an enrollment document or a student ID photo.",
            )

        normalized_email = self._normalize_email(email)
        normalized_personal_email = self._normalize_email(personal_email)

        if self._domain_is_university(normalized_personal_email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Personal email must not be a university email.",
            )

        canonical_university = self._lookup_verified_university(normalized_email)
        date_of_birth_iso, age = self._parse_date_of_birth(date_of_birth)

        try:
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
        except PydanticValidationError as exc:
            message = str(exc.errors()[0].get("msg") or "Invalid signup details")
            if message.startswith("Value error, "):
                message = message[len("Value error, "):]
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=message,
            ) from exc

        blacklist = fetch_one("SELECT email FROM user_blacklist WHERE email = %s", (normalized_email,))
        if blacklist:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "ACCOUNT_SUSPENDED",
                    "message": "Your account was suspended due to repeated rejections. Please email support@studentverse.ae to rectify this.",
                    "verification_status": "suspended",
                },
            )

        existing = fetch_one("SELECT id, verification_status FROM users WHERE email = %s", (normalized_email,))
        if existing:
            existing_status = existing.get("verification_status") or "approved"
            if existing_status == "suspended":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"code": "ACCOUNT_SUSPENDED", "message": "Your account was suspended due to repeated rejections.", "verification_status": "suspended"},
                )
            if existing_status == "pending_review":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"code": "ACCOUNT_PENDING_REVIEW", "message": "Your account is already under review.", "verification_status": "pending_review"},
                )
            if existing_status == "rejected":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"code": "ACCOUNT_REJECTED", "message": "Your account was rejected. Please resubmit your documents instead.", "verification_status": "rejected"},
                )
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists. Please use the login screen.")

        personal_dup = fetch_one("SELECT id FROM users WHERE personal_email = %s LIMIT 1", (normalized_personal_email,))
        if personal_dup:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This personal email is already linked to another account.",
            )

        enrollment_payload = await self._read_verification_file(enrollment_document, "Enrollment document") if enrollment_document else None
        student_id_payload = await self._read_verification_file(student_id_document, "Student ID document") if student_id_document else None

        verification_status = "pending_review"
        signup_method = "manual_review"
        if automated_verification:
            await self._verify_automated_signup(
                enrollment_payload=enrollment_payload,
                student_id_payload=student_id_payload,
                first_name=first_name,
                last_name=last_name,
                university=canonical_university,
            )
            verification_status = "approved"
            signup_method = "automated_ai"

        self._consume_signup_token(normalized_personal_email, signup_token)

        user_id = str(uuid.uuid4())
        submission_id = None
        uploaded_paths: list[str] = []

        try:
            self._insert_user_row_for_signup(
                user_id=user_id,
                payload=register_request,
                age=age,
                signup_method=signup_method,
                verification_status=verification_status,
                personal_email=normalized_personal_email,
            )

            submission_res = fetch_one(
                "INSERT INTO user_verification_submissions (user_id, status) VALUES (%s, %s) RETURNING id",
                (user_id, verification_status)
            )
            if not submission_res:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create verification record.")
            submission_id = str(submission_res["id"])

            enrollment_path = None
            if enrollment_payload:
                enrollment_path = self._upload_verification_document(
                    user_id=user_id,
                    submission_id=submission_id,
                    slug="enrollment",
                    payload=enrollment_payload,
                )
                uploaded_paths.append(enrollment_path)

            student_id_path = None
            if student_id_payload:
                student_id_path = self._upload_verification_document(
                    user_id=user_id,
                    submission_id=submission_id,
                    slug="student-id",
                    payload=student_id_payload,
                )
                uploaded_paths.append(student_id_path)

            execute(
                "UPDATE user_verification_submissions SET enrollment_document_path = %s, student_id_document_path = %s WHERE id = %s",
                (enrollment_path, student_id_path, submission_id)
            )

            mark_signup_versions(user_id, app_version=app_version, platform=platform)

            if verification_status == "approved":
                mark_login(user_id, app_version=app_version, platform=platform)
                access_token = create_access_token(user_id, normalized_email)
                return {
                    "status": "approved",
                    "verification_status": "approved",
                    "message": "Documents verified successfully. You can now start using StudentVerse.",
                    "access_token": access_token,
                    "token_type": "bearer",
                    "user": {"id": user_id, "email": normalized_email, "name": register_request.name},
                }

            self._send_review_email(email_service.send_review_received_email, normalized_email, register_request.first_name)
            return {
                "status": "pending_review",
                "verification_status": "pending_review",
                "message": "Your application has been submitted for manual review.",
                "user": {"id": user_id, "email": normalized_email, "name": register_request.name},
            }

        except Exception as e:
            for p in uploaded_paths:
                self._delete_storage_object(p)
            if submission_id:
                execute("DELETE FROM user_verification_submissions WHERE id = %s", (submission_id,))
            execute("DELETE FROM users WHERE id = %s", (user_id,))
            if isinstance(e, HTTPException):
                raise
            logger.error(f"Manual signup unexpected error: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to submit account for review. Please try again.")

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
        enrollment_payload = await self._read_verification_file(enrollment_document, "Enrollment document") if enrollment_document else None
        student_id_payload = await self._read_verification_file(student_id_document, "Student ID document") if student_id_document else None

        user = fetch_one("SELECT id, email, password_hash, verification_status FROM users WHERE email = %s", (normalized_email,))
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No account found with this email.")

        if user.get("verification_status") != "rejected":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only rejected accounts can resubmit documents.",
            )

        stored_hash = user.get("password_hash")
        if not stored_hash or not bcrypt_hasher.verify(password, stored_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

        user_id = str(user["id"])
        submission_id = None
        uploaded_paths: list[str] = []

        try:
            submission_insert = fetch_one(
                "INSERT INTO user_verification_submissions (user_id, status) VALUES (%s, %s) RETURNING id",
                (user_id, "pending_review")
            )
            submission_id = str(submission_insert["id"])

            enrollment_path = None
            if enrollment_payload:
                enrollment_path = self._upload_verification_document(
                    user_id=user_id,
                    submission_id=submission_id,
                    slug="enrollment",
                    payload=enrollment_payload,
                )
                uploaded_paths.append(enrollment_path)

            student_id_path = None
            if student_id_payload:
                student_id_path = self._upload_verification_document(
                    user_id=user_id,
                    submission_id=submission_id,
                    slug="student-id",
                    payload=student_id_payload,
                )
                uploaded_paths.append(student_id_path)

            execute(
                "UPDATE user_verification_submissions SET enrollment_document_path = %s, student_id_document_path = %s WHERE id = %s",
                (enrollment_path, student_id_path, submission_id)
            )

            execute(
                "UPDATE users SET verification_status = 'pending_review', verification_rejection_reason = NULL, verification_submitted_at = %s WHERE id = %s",
                (datetime.now(timezone.utc).isoformat(), user_id)
            )

            self._send_review_email(email_service.send_review_received_email, normalized_email, "")
            return {
                "status": "pending_review",
                "verification_status": "pending_review",
                "message": "Your documents have been resubmitted for review.",
            }

        except Exception as e:
            for p in uploaded_paths:
                self._delete_storage_object(p)
            if submission_id:
                execute("DELETE FROM user_verification_submissions WHERE id = %s", (submission_id,))
            if isinstance(e, HTTPException):
                raise
            logger.error(f"Manual resubmit error: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to resubmit documents. Please try again.")

    async def complete_registration(self, user_id: str, request: RegisterRequest, access_token: str = None) -> Dict[str, Any]:
        """Complete registration by saving password and profile fields to users table."""
        try:
            password_to_set = request.password
            if password_to_set:
                pw_hash = bcrypt_hasher.hash(password_to_set)
                execute("UPDATE users SET password_hash = %s WHERE id = %s", (pw_hash, user_id))
                logger.info(f"Password set for user: {user_id}")

            ALLOWED_DB_FIELDS = {
                "first_name", "last_name", "name", "nationality", "university",
                "phone_number", "age", "date_of_birth", "student_id", "device_id"
            }
            raw_data = request.model_dump(exclude_unset=True, by_alias=True)
            raw_data.pop("email", None)
            raw_data.pop("password", None)
            avatar_url = raw_data.pop("avatar_url", None)

            update_data = {k: v for k, v in raw_data.items() if k in ALLOWED_DB_FIELDS}
            update_data["account_type"] = "free"
            update_data["logged_in"] = True
            if avatar_url:
                update_data["avatar_url"] = avatar_url

            set_clauses = [f"{k} = %s" for k in update_data.keys()]
            sql = f"UPDATE users SET {', '.join(set_clauses)} WHERE id = %s RETURNING *"
            profile = fetch_one(sql, tuple(update_data.values()) + (user_id,))
            if not profile:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User profile not found. Please verify OTP first.")

            logger.info(f"Registration completed for user: {user_id}")
            new_access_token = create_access_token(user_id, profile["email"])
            profile["access_token"] = new_access_token
            profile["token_type"] = "bearer"
            return profile

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Registration completion error: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update profile.")

    async def login(
        self,
        email: str,
        password: str,
        device_id: str = "",
        *,
        app_version: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> Dict:
        """Authenticate with email + password using local bcrypt and issue JWT."""
        email = self._normalize_email(email)
        user_row = fetch_one(
            "SELECT id, email, personal_email, name, first_name, last_name, student_id, nationality, university, phone_number, age, date_of_birth, avatar_url, account_type, created_at, verification_status, verification_rejection_reason, password_hash FROM users WHERE email = %s",
            (email,)
        )
        if not user_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No account found with this email. Please sign up first.")

        stored_hash = user_row.get("password_hash")
        if not stored_hash:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "PASSWORD_RESET_REQUIRED", "message": "Please reset your password to continue with your new Azure login."}
            )

        if not bcrypt_hasher.verify(password, stored_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

        user_id = str(user_row["id"])
        verification_status = user_row.get("verification_status") or "approved"
        if verification_status != "approved":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=self._build_review_error_detail(user_row))

        if device_id:
            execute("UPDATE users SET logged_in = true, device_id = %s WHERE id = %s", (device_id, user_id))
        else:
            execute("UPDATE users SET logged_in = true WHERE id = %s", (user_id,))

        mark_login(user_id, app_version=app_version, platform=platform)

        access_token = create_access_token(user_id, email)
        refresh_token = create_access_token(user_id, email)

        user_payload = {"id": user_id, "email": email}
        for field in (
            "personal_email", "name", "first_name", "last_name", "student_id",
            "nationality", "university", "phone_number", "age", "date_of_birth",
            "avatar_url", "account_type", "created_at",
        ):
            if field in user_row:
                user_payload[field] = user_row.get(field)

        return {
            "status": "success",
            "message": "Login successful",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": 3600 * 24 * 30,
            "token_type": "bearer",
            "user": user_payload,
        }

    async def update_profile(self, user_id: str, request: ProfileUpdateRequest) -> Dict[str, Any]:
        """Update public.users row with non-None fields."""
        fields = request.model_dump(exclude_unset=True)
        if not fields:
            user = fetch_one("SELECT * FROM users WHERE id = %s", (user_id,))
            return user or {}

        set_clauses = [f"{k} = %s" for k in fields.keys()]
        sql = f"UPDATE users SET {', '.join(set_clauses)} WHERE id = %s RETURNING *"
        profile = fetch_one(sql, tuple(fields.values()) + (user_id,))
        if not profile:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User profile not found")
        return profile

    async def get_profile(self, user_id: str) -> Dict[str, Any]:
        """Fetch a single public.users row by id."""
        user = fetch_one("SELECT * FROM users WHERE id = %s", (user_id,))
        if not user:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
        return user

    async def upload_profile_image(self, user_id: str, upload: UploadFile) -> Dict[str, Any]:
        """Upload a profile picture to Azure Blob Storage and update users.avatar_url."""
        if not upload or not upload.filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Profile image is required.")

        mime_type = (upload.content_type or "").lower()
        if mime_type not in ALLOWED_PROFILE_IMAGE_MIME_TYPES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Profile image must be a JPG, PNG, or WEBP file.")

        data = await upload.read()
        await upload.close()

        if not data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Profile image is empty.")

        if len(data) > PROFILE_IMAGE_MAX_BYTES:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Profile image exceeds the 5MB limit.")

        extension = os.path.splitext(upload.filename)[1].lower() or ".jpg"
        timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        path = f"{user_id}/pfp-{timestamp_ms}{extension}"

        try:
            upload_blob(PROFILE_IMAGE_BUCKET_NAME, path, data, mime_type)
        except Exception as e:
            logger.error(f"Failed to upload profile image {path}: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to upload profile image.")

        avatar_url = get_blob_url(PROFILE_IMAGE_BUCKET_NAME, path)
        execute("UPDATE users SET avatar_url = %s WHERE id = %s", (avatar_url, user_id))
        return {"avatar_url": avatar_url, "storage_path": path}

    async def get_user_analytics(self, user_id: str) -> UserStats:
        """Calculate user analytics from redemptions."""
        try:
            data = fetch_all(
                "SELECT discount_amount, total_bill_amount, final_amount FROM redemptions WHERE user_id = %s AND is_voided = false",
                (user_id,)
            )
            total_saved = sum(float(r.get("discount_amount") or 0) for r in data)
            total_spent = sum(float(r.get("total_bill_amount") or 0) for r in data)
            total_redemptions = len(data)

            user_res = fetch_one("SELECT account_type FROM users WHERE id = %s", (user_id,))
            sub_status = (user_res.get("account_type") or "free") if user_res else "free"

            return UserStats(
                total_saved=total_saved,
                total_spent=total_spent,
                total_redemptions=total_redemptions,
                subscription_status=sub_status
            )
        except Exception as e:
            logger.error(f"Analytics error: {e}")
            return UserStats()

    async def logout_user(
        self,
        user_id: str,
        access_token: str = None,
        *,
        app_version: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> None:
        """Log out user: clear logged_in and device_id."""
        try:
            execute("UPDATE users SET logged_in = false, device_id = NULL WHERE id = %s", (user_id,))
            logger.info(f"User logged out: {user_id}")
        except Exception as e:
            logger.error(f"Logout DB update error: {e}")

        log_activity_event(user_id, "logout", app_version=app_version, platform=platform)

    async def delete_account(self, user_id: str, access_token: str = None) -> None:
        """Permanently delete a user account and all associated data."""
        try:
            execute("DELETE FROM redemptions WHERE user_id = %s", (user_id,))
            execute("DELETE FROM entitlements WHERE user_id = %s", (user_id,))
            execute("DELETE FROM ticket_records WHERE user_id = %s", (user_id,))
            execute("DELETE FROM user_push_tokens WHERE user_id = %s", (user_id,))
            execute("DELETE FROM user_activity_events WHERE user_id = %s", (user_id,))
            execute("DELETE FROM user_verification_submissions WHERE user_id = %s", (user_id,))
            execute("DELETE FROM users WHERE id = %s", (user_id,))
            logger.info(f"Permanently deleted account: {user_id}")
        except Exception as e:
            logger.error(f"Failed to delete account {user_id}: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete account.")

    async def list_verified_institutions(self) -> list:
        """Return list of active verified universities for frontend dropdown."""
        try:
            return fetch_all("SELECT university_name, domain FROM university_domains WHERE is_active = true ORDER BY university_name")
        except Exception as e:
            logger.error(f"Failed to fetch institutions: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to load institutions")

    def _validate_azure_token(self, access_token: str):
        email = None
        try:
            from jose import jwt as jose_jwt
            claims = jose_jwt.get_unverified_claims(access_token)
            email = claims.get("email") or claims.get("preferred_username") or claims.get("upn")
        except Exception:
            pass

        if not email:
            try:
                resp = httpx.get(
                    "https://graph.microsoft.com/v1.0/me",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=10.0
                )
                if resp.status_code == 200:
                    data = resp.json()
                    email = data.get("mail") or data.get("userPrincipalName")
            except Exception as e:
                logger.error(f"Microsoft Graph API call failed: {e}")

        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired authentication session"
            )

        email = email.lower().strip()
        try:
            domain = email.split("@")[1]
        except IndexError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email format")

        university_name = self._lookup_verified_university(email)
        return {"email": email, "id": str(uuid.uuid4())}, email, domain, university_name

    async def verify_microsoft_signup(self, access_token: str) -> Dict[str, Any]:
        auth_user, email, domain, university_name = self._validate_azure_token(access_token)
        existing = fetch_one("SELECT id FROM users WHERE email = %s", (email,))
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists. Please use the login screen."
            )

        user_id = str(uuid.uuid4())
        execute(
            "INSERT INTO users (id, email, account_type, verification_status, signup_method) VALUES (%s, %s, 'free', 'approved', 'azure_oauth')",
            (user_id, email)
        )
        new_access_token = create_access_token(user_id, email)
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
        auth_user, email, domain, university_name = self._validate_azure_token(access_token)
        user_check = fetch_one("SELECT id FROM users WHERE email = %s", (email,))
        if not user_check:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No account found with this email.")

        user_id = str(user_check["id"])
        reset_token = str(uuid.uuid4())
        redis_manager.setex(f"sv:app:auth:reset_token:{user_id}", 600, reset_token)
        return {"email": email, "reset_token": reset_token}

    async def approve_verification_submission(self, submission_id: str, reviewer: str) -> Dict[str, Any]:
        submission = fetch_one(
            "SELECT s.*, u.email as user_email FROM user_verification_submissions s JOIN users u ON u.id = s.user_id WHERE s.id = %s",
            (submission_id,)
        )
        if not submission:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification submission not found.")

        if submission.get("status") != "pending_review":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This verification submission has already been reviewed.")

        reviewed_at = datetime.now(timezone.utc).isoformat()
        user_id = str(submission["user_id"])
        user_email = submission["user_email"]

        execute(
            "UPDATE user_verification_submissions SET status = 'approved', reviewed_by = %s, reviewed_at = %s, rejection_reason = NULL WHERE id = %s",
            (reviewer, reviewed_at, submission_id)
        )
        execute(
            "UPDATE users SET verification_status = 'approved', verification_reviewed_at = %s, verification_reviewed_by = %s, verification_rejection_reason = NULL WHERE id = %s",
            (reviewed_at, reviewer, user_id)
        )

        self._send_review_email(email_service.send_review_approved_email, user_email)
        await self._send_review_push(user_id, approved=True)

        return {
            "submission_id": submission_id,
            "user_id": user_id,
            "verification_status": "approved",
        }

    async def reject_verification_submission(self, submission_id: str, reviewer: str, reason: str) -> Dict[str, Any]:
        submission = fetch_one(
            "SELECT s.*, u.email as user_email FROM user_verification_submissions s JOIN users u ON u.id = s.user_id WHERE s.id = %s",
            (submission_id,)
        )
        if not submission:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification submission not found.")

        if submission.get("status") != "pending_review":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This verification submission has already been reviewed.")

        reviewed_at = datetime.now(timezone.utc).isoformat()
        user_id = str(submission["user_id"])
        user_email = submission["user_email"]

        execute(
            "UPDATE user_verification_submissions SET status = 'rejected', reviewed_by = %s, reviewed_at = %s, rejection_reason = %s WHERE id = %s",
            (reviewer, reviewed_at, reason, submission_id)
        )
        execute(
            "UPDATE users SET verification_status = 'rejected', verification_reviewed_at = %s, verification_reviewed_by = %s, verification_rejection_reason = %s WHERE id = %s",
            (reviewed_at, reviewer, reason, user_id)
        )

        self._send_review_email(email_service.send_review_rejected_email, user_email, reason)
        await self._send_review_push(user_id, approved=False)

        return {
            "submission_id": submission_id,
            "user_id": user_id,
            "verification_status": "rejected",
            "review_reason": reason,
        }


auth_service = AuthService()
