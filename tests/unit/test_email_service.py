"""
Unit tests for email service
"""

import pytest
from unittest.mock import patch, MagicMock
from app.core.email import EmailService, email_service


class TestEmailService:
    """Test email service functionality"""
    
    @patch('app.core.email.resend.Emails.send')
    @patch('app.core.email.RESEND_API_KEY', 'test_api_key')
    def test_send_otp_email_success(self, mock_send):
        """Test successful OTP email sending"""
        # Arrange
        mock_send.return_value = {"id": "test_email_id"}
        email = "test@university.edu"
        otp_code = "123456"
        
        # Act
        result = email_service.send_otp_email(email, otp_code)
        
        # Assert
        assert result is True
        mock_send.assert_called_once()
        call_args = mock_send.call_args[0][0]
        assert call_args["to"] == [email]
        assert otp_code in call_args["text"]
        assert "StudentVerse" in call_args["subject"]
    
    @patch('app.core.email.resend.Emails.send')
    @patch('app.core.email.RESEND_API_KEY', 'test_api_key')
    def test_send_otp_email_with_custom_expiry(self, mock_send):
        """Test OTP email with custom expiry time"""
        # Arrange
        mock_send.return_value = {"id": "test_email_id"}
        email = "test@university.edu"
        otp_code = "654321"
        expiry_minutes = 10
        
        # Act
        result = email_service.send_otp_email(email, otp_code, expiry_minutes)
        
        # Assert
        assert result is True
        call_args = mock_send.call_args[0][0]
        assert f"{expiry_minutes} minutes" in call_args["text"]
    
    @patch('app.core.email.resend.Emails.send')
    @patch('app.core.email.RESEND_API_KEY', 'test_api_key')
    def test_send_otp_email_failure(self, mock_send):
        """Test email sending failure"""
        # Arrange
        mock_send.side_effect = Exception("Resend API error")
        email = "test@university.edu"
        otp_code = "123456"
        
        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            email_service.send_otp_email(email, otp_code)
        
        assert "Failed to send verification email" in str(exc_info.value)
    
    @patch('app.core.email.RESEND_API_KEY', None)
    def test_send_otp_email_no_api_key(self):
        """Test email sending without API key configured"""
        # Arrange
        email = "test@university.edu"
        otp_code = "123456"
        
        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            email_service.send_otp_email(email, otp_code)
        
        assert "Email service not configured" in str(exc_info.value)
    
    @patch('app.core.email.resend.Emails.send')
    @patch('app.core.email.RESEND_API_KEY', 'test_api_key')
    def test_email_content_format(self, mock_send):
        """Test that email content is plain text only"""
        # Arrange
        mock_send.return_value = {"id": "test_email_id"}
        email = "test@university.edu"
        otp_code = "999888"
        
        # Act
        email_service.send_otp_email(email, otp_code)
        
        # Assert
        call_args = mock_send.call_args[0][0]
        # Verify plain text format
        assert "text" in call_args
        assert "html" not in call_args
        # Verify no links in content
        assert "http" not in call_args["text"]
        assert "https" not in call_args["text"]
