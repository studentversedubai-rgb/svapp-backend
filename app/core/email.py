"""
Email Service

Handles email delivery using Resend SDK v2.7.0 (pinned).
"""

import os
import logging
import resend

logger = logging.getLogger(__name__)

# Configure Resend at module load time
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM = os.getenv("RESEND_FROM", "auth@loginotp.studentverse.app")

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY
    logger.info(f"Resend initialised. From: {RESEND_FROM}")
else:
    logger.warning("RESEND_API_KEY not found in environment variables")


class EmailService:
    """Handles email operations via Resend."""

    @staticmethod
    def send_otp_email(email: str, otp_code: str, expiry_minutes: int = 5) -> bool:
        """
        Send OTP verification email via Resend SDK 2.x.

        Uses the typed-dict style required by SDK >=2.0.
        Explicitly checks the return value for errors (send() does NOT always raise
        on failure — it can return an error dict instead).

        Raises:
            Exception: with the full Resend detail so it surfaces in Railway logs.
        """
        if not RESEND_API_KEY:
            logger.error("Cannot send email: RESEND_API_KEY not configured")
            raise Exception("Email service not configured: RESEND_API_KEY missing")

        email_body = f"""Your StudentVerse verification code is:

{otp_code}

This code will expire in {expiry_minutes} minutes.

If you didn't request this code, please ignore this email.

---
StudentVerse Team
"""

        # SDK 2.x typed-dict style (required from v2.0 onwards)
        params: resend.Emails.SendParams = {
            "from": RESEND_FROM,
            "to": [email],
            "subject": "Your StudentVerse Verification Code",
            "text": email_body,
        }

        try:
            logger.info(f"Attempting Resend send to {email} from {RESEND_FROM}")
            result = resend.Emails.send(params)
            logger.info(f"Resend raw result: {result}")

            # SDK 2.x returns a dict — success has an 'id' field, failure does not
            if not result or "id" not in result:
                error_detail = result if result else "empty response"
                logger.error(f"Resend returned no email ID (silent failure): {error_detail}")
                raise Exception(f"Resend send failed (no id in response): {error_detail}")

            logger.info(f"OTP email sent to {email}. Resend ID: {result['id']}")
            return True

        except Exception as e:
            # Log the FULL original error so it appears clearly in Railway logs
            logger.error(
                f"Resend send failed. To: {email}, From: {RESEND_FROM}, "
                f"ErrorType: {type(e).__name__}, Detail: {str(e)}",
                exc_info=True
            )
            # Re-raise the real error (not a generic wrapper)
            raise Exception(f"Resend error [{type(e).__name__}]: {str(e)}")


# Singleton instance
email_service = EmailService()
