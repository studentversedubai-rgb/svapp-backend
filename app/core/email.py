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

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>StudentVerse Verification Code</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: #000000;
            color: #ffffff;
            line-height: 1.6;
            padding: 20px;
        }}
        .container {{
            max-width: 480px;
            margin: 0 auto;
            background-color: rgba(18, 18, 18, 0.6);
            border-radius: 20px;
            overflow: hidden;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        .header {{
            background: linear-gradient(90deg, #FF6B35 0%, #F72585 50%, #7209B7 100%);
            padding: 32px 24px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 28px;
            font-weight: 800;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 2px;
        }}
        .header .subtitle {{
            font-size: 14px;
            opacity: 0.9;
            font-weight: 500;
        }}
        .content {{
            padding: 32px 24px;
        }}
        .greeting {{
            margin-bottom: 24px;
        }}
        .greeting p {{
            font-size: 16px;
            color: #ffffff;
            margin-bottom: 8px;
        }}
        .greeting p:first-child {{
            font-size: 20px;
            font-weight: 700;
            color: #9C27B0;
        }}
        .otp-container {{
            background: linear-gradient(135deg, #FF6B35 0%, #F72585 50%, #7209B7 100%);
            border-radius: 16px;
            padding: 3px;
            margin: 32px 0;
        }}
        .otp-inner {{
            background-color: #121212;
            border-radius: 14px;
            padding: 32px 24px;
            text-align: center;
        }}
        .otp-label {{
            font-size: 14px;
            color: #888888;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            font-weight: 600;
            margin-bottom: 16px;
        }}
        .otp-code {{
            font-size: 48px;
            font-weight: 800;
            letter-spacing: 8px;
            background: linear-gradient(90deg, #FF6B35 0%, #F72585 50%, #B537F2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin: 16px 0;
        }}
        .otp-expiry {{
            font-size: 14px;
            color: #888888;
            margin-top: 16px;
        }}
        .security-notice {{
            background-color: rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            padding: 20px;
            margin: 24px 0;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        .security-notice p {{
            font-size: 14px;
            color: #888888;
            line-height: 1.5;
        }}
        .security-notice p strong {{
            color: #ffffff;
            font-weight: 600;
        }}
        .footer {{
            background-color: #000000;
            padding: 24px;
            text-align: center;
            border-top: 1px solid rgba(255, 255, 255, 0.08);
        }}
        .footer p {{
            color: #888888;
            font-size: 13px;
            margin-bottom: 6px;
            line-height: 1.5;
        }}
        .footer .brand {{
            background: linear-gradient(90deg, #FF6B35 0%, #F72585 50%, #7209B7 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            font-weight: 700;
            font-size: 16px;
            margin-top: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        @media (max-width: 480px) {{
            body {{
                padding: 12px;
            }}
            .container {{
                border-radius: 16px;
            }}
            .otp-code {{
                font-size: 40px;
                letter-spacing: 6px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Verification Code</h1>
            <p class="subtitle">Secure your account</p>
        </div>
        
        <div class="content">
            <div class="greeting">
                <p>Hello,</p>
                <p>Here is your StudentVerse verification code. Use it to complete your university email verification.</p>
            </div>
            
            <div class="otp-container">
                <div class="otp-inner">
                    <div class="otp-label">Your Code</div>
                    <div class="otp-code">{otp_code}</div>
                    <div class="otp-expiry">Expires in {expiry_minutes} minutes</div>
                </div>
            </div>
            
            <div class="security-notice">
                <p><strong>Security Notice:</strong> If you didn't request this verification code, please ignore this email. Someone may have entered your email address by mistake.</p>
            </div>
        </div>
        
        <div class="footer">
            <p>This is an automated message from StudentVerse.</p>
            <p>Do not reply to this email.</p>
            <p class="brand">StudentVerse</p>
        </div>
    </div>
</body>
</html>"""

        plain_text = f"""Your StudentVerse verification code is:

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
                HtmlBody=html_content,
                TextBody=plain_text,
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
