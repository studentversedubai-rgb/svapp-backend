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
else:
    logger.warning("RESEND_API_KEY not found in environment variables")


class EmailService:
    """Handles email operations"""
    
    @staticmethod
    def send_otp_email(email: str, otp_code: str, expiry_minutes: int = 5) -> bool:
        """
        Send OTP verification email
        
        Args:
            email: Recipient email address
            otp_code: 6-digit OTP code
            expiry_minutes: OTP expiry time in minutes
            
        Returns:
            True if email sent successfully
            
        Raises:
            Exception: If email sending fails
        """
        if not RESEND_API_KEY:
            logger.error("Cannot send email: RESEND_API_KEY not configured")
            raise Exception("Email service not configured")
        
        # Plain text email content
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
            
            response = resend.Emails.send(params)
            logger.info(f"OTP email sent successfully to {email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send OTP email to {email}: {str(e)}")
            raise Exception("Failed to send verification email")


# Singleton instance
email_service = EmailService()
