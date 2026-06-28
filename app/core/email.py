"""
Email Service

Handles email delivery using Postmark.
"""

import os
import logging
from postmarker.core import PostmarkClient

logger = logging.getLogger(__name__)

POSTMARK_API_KEY = os.getenv("POSTMARK_API_KEY", "")
FROM_ADDRESS = os.getenv("REVIEW_FROM_ADDRESS", "verify@studentverseofficial.com")

if not POSTMARK_API_KEY:
    logger.warning("POSTMARK_API_KEY not found in environment variables")


class EmailService:
    """Handles email operations via Postmark."""

    @staticmethod
    def _send_text_email(email: str, subject: str, body: str) -> bool:
        if not POSTMARK_API_KEY:
            logger.error("Cannot send email: POSTMARK_API_KEY not configured")
            raise Exception("Email service not configured: POSTMARK_API_KEY missing")

        try:
            client = PostmarkClient(server_token=POSTMARK_API_KEY)
            logger.info(f"Attempting Postmark send to {email} from {FROM_ADDRESS}")

            result = client.emails.send(
                From=FROM_ADDRESS,
                To=email,
                Subject=subject,
                TextBody=body,
            )

            logger.info(f"Email sent to {email}. Subject: {subject}. Postmark result: {result}")
            return True

        except Exception as e:
            logger.error(
                f"Postmark send failed. To: {email}, From: {FROM_ADDRESS}, "
                f"ErrorType: {type(e).__name__}, Detail: {str(e)}",
                exc_info=True
            )
            raise Exception(f"Postmark error [{type(e).__name__}]: {str(e)}")

    @staticmethod
    def send_otp_email(email: str, otp_code: str, expiry_minutes: int = 5) -> bool:
        """
        Send OTP verification email via Postmark.

        Raises:
            Exception: with full Postmark error detail so it surfaces in Railway logs.
        """
        plain_text = f"Your StudentVerse OTP code is: {otp_code}\n\nExpires in {expiry_minutes} minutes."
        return EmailService._send_text_email(email, "Verification Code", plain_text)

    @staticmethod
    def send_review_submission_email(email: str) -> bool:
        body = (
            "Your StudentVerse account submission is under review.\n\n"
            "We received your enrollment and student ID documents. "
            "Our team will review them and email you once your account is approved or if we need anything else."
        )
        return EmailService._send_text_email(email, "StudentVerse account under review", body)

    @staticmethod
    def send_review_resubmitted_email(email: str) -> bool:
        body = (
            "We received your updated StudentVerse verification documents.\n\n"
            "Your account is back under review. We will email you after the new review is complete."
        )
        return EmailService._send_text_email(email, "StudentVerse review resubmitted", body)

    @staticmethod
    def send_review_approved_email(email: str) -> bool:
        body = (
            "Your StudentVerse account has been approved.\n\n"
            "You can now log in with the email and password you used during signup."
        )
        return EmailService._send_text_email(email, "StudentVerse account approved", body)

    @staticmethod
    def send_review_rejected_email(email: str, reason: str) -> bool:
        body = (
            "Your StudentVerse account review needs updated documents.\n\n"
            f"Reason: {reason}\n\n"
            "Please reopen the app, log in, and resubmit your documents."
        )
        return EmailService._send_text_email(email, "StudentVerse documents need attention", body)


# Singleton instance
email_service = EmailService()
