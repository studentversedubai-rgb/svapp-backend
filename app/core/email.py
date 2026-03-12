"""
Email Service

Handles email delivery using Resend.
"""

import os
import logging
from typing import Optional
import resend

logger = logging.getLogger(__name__)

# Configure Resend
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM = os.getenv("RESEND_FROM", "auth@loginotp.studentverse.app")

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY
    logger.info(f"Resend configured with from address: {RESEND_FROM}")
else:
    logger.warning("RESEND_API_KEY not found in environment variables")


class EmailService:
    """Handles email operations via Resend."""

    @staticmethod
    def send_otp_email(email: str, otp_code: str, expiry_minutes: int = 5) -> bool:
        """
        Send OTP verification email.

        Raises:
            Exception: with the FULL Resend error detail so it surfaces in logs.
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

        try:
            params = {
                "from": RESEND_FROM,
                "to": [email],
                "subject": "Your StudentVerse Verification Code",
                "text": email_body,
            }

            logger.info(f"Sending OTP email to {email} from {RESEND_FROM}")
            response = resend.Emails.send(params)
            logger.info(f"Resend response: {response}")
            logger.info(f"OTP email sent successfully to {email}")
            return True

        except Exception as e:
            # Log the FULL original exception so we can actually diagnose Resend issues
            logger.error(f"Resend send failed to {email}. Error type: {type(e).__name__}. Detail: {str(e)}", exc_info=True)
            # Re-raise the original error (not a generic one) so it appears in Railway logs
            raise Exception(f"Resend error: {str(e)}")


# Singleton instance
email_service = EmailService()
