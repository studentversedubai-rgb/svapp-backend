"""
Email Service

Handles email delivery using Postmark.
"""

import os
import logging
from postmarker.core import PostmarkClient

logger = logging.getLogger(__name__)

POSTMARK_API_KEY = os.getenv("POSTMARK_API_KEY")
FROM_ADDRESS = "verify@studentverseofficial.com"

if not POSTMARK_API_KEY:
    logger.warning("POSTMARK_API_KEY not found in environment variables")


class EmailService:
    """Handles email operations via Postmark."""

    @staticmethod
    def send_otp_email(email: str, otp_code: str, expiry_minutes: int = 5) -> bool:
        """
        Send OTP verification email via Postmark.

        Raises:
            Exception: with full Postmark error detail so it surfaces in Railway logs.
        """
        if not POSTMARK_API_KEY:
            logger.error("Cannot send email: POSTMARK_API_KEY not configured")
            raise Exception("Email service not configured: POSTMARK_API_KEY missing")

        plain_text = f"Your StudentVerse OTP code is: {otp_code}\n\nExpires in {expiry_minutes} minutes."

        try:
            client = PostmarkClient(server_token=POSTMARK_API_KEY)
            logger.info(f"Attempting Postmark send to {email} from {FROM_ADDRESS}")

            result = client.emails.send(
                From=FROM_ADDRESS,
                To=email,
                Subject="Verification Code",
                TextBody=plain_text,
            )

            logger.info(f"OTP email sent to {email}. Postmark result: {result}")
            return True

        except Exception as e:
            logger.error(
                f"Postmark send failed. To: {email}, From: {FROM_ADDRESS}, "
                f"ErrorType: {type(e).__name__}, Detail: {str(e)}",
                exc_info=True
            )
            raise Exception(f"Postmark error [{type(e).__name__}]: {str(e)}")


# Singleton instance
email_service = EmailService()