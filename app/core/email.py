"""
Email Service

Handles email delivery using Postmark.
"""

import os
import logging
from postmarker.core import PostmarkClient

logger = logging.getLogger(__name__)

POSTMARK_API_KEY = os.getenv("POSTMARK_API_KEY")
FROM_ADDRESS = "support@studentverse.app"

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

        email_body = f"""Your StudentVerse verification code is:

{otp_code}

This code will expire in {expiry_minutes} minutes.

If you didn't request this code, please ignore this email.

---
StudentVerse Team
"""

        try:
            client = PostmarkClient(server_token=POSTMARK_API_KEY)
            logger.info(f"Attempting Postmark send to {email} from {FROM_ADDRESS}")

            result = client.emails.send(
                From=FROM_ADDRESS,
                To=email,
                Subject="Your StudentVerse Verification Code",
                TextBody=email_body,
            )

            logger.info(f"Postmark raw result: {result}")

            # Postmark returns a dict — success has 'MessageID' and 'ErrorCode' == 0
            error_code = result.get("ErrorCode", -1) if isinstance(result, dict) else -1
            if error_code != 0:
                logger.error(f"Postmark returned an error: {result}")
                raise Exception(f"Postmark send failed: {result}")

            logger.info(f"OTP email sent to {email}. Postmark MessageID: {result.get('MessageID')}")
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
