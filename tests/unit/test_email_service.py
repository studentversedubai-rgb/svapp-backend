"""
Unit tests for email service (Postmark implementation)
"""

import pytest
from unittest.mock import patch, MagicMock
from app.core.email import EmailService, email_service


class TestEmailService:
    """Test email service functionality using Postmark"""
    
    @patch('app.core.email.PostmarkClient')
    @patch('app.core.email.POSTMARK_API_KEY', 'test_postmark_api_key')
    def test_send_otp_email_success(self, mock_client_class):
        """Test successful OTP email sending"""
        # Arrange
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.emails.send.return_value = {"MessageID": "test_email_id"}
        email = "test@university.edu"
        otp_code = "123456"
        
        # Act
        result = email_service.send_otp_email(email, otp_code)
        
        # Assert
        assert result is True
        mock_client.emails.send.assert_called_once()
        call_kwargs = mock_client.emails.send.call_args[1]
        assert call_kwargs["To"] == email
        assert otp_code in call_kwargs["TextBody"]
        assert "Verification Code" in call_kwargs["Subject"]
    
    @patch('app.core.email.PostmarkClient')
    @patch('app.core.email.POSTMARK_API_KEY', 'test_postmark_api_key')
    def test_send_otp_email_with_custom_expiry(self, mock_client_class):
        """Test OTP email with custom expiry time"""
        # Arrange
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.emails.send.return_value = {"MessageID": "test_email_id"}
        email = "test@university.edu"
        otp_code = "654321"
        expiry_minutes = 10
        
        # Act
        result = email_service.send_otp_email(email, otp_code, expiry_minutes)
        
        # Assert
        assert result is True
        call_kwargs = mock_client.emails.send.call_args[1]
        assert f"{expiry_minutes} minutes" in call_kwargs["TextBody"]
    
    @patch('app.core.email.PostmarkClient')
    @patch('app.core.email.POSTMARK_API_KEY', 'test_postmark_api_key')
    def test_send_otp_email_failure(self, mock_client_class):
        """Test email sending failure"""
        # Arrange
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.emails.send.side_effect = Exception("Postmark API error")
        email = "test@university.edu"
        otp_code = "123456"
        
        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            email_service.send_otp_email(email, otp_code)
        
        assert "Postmark error" in str(exc_info.value)
    
    @patch('app.core.email.POSTMARK_API_KEY', '')
    def test_send_otp_email_no_api_key(self):
        """Test email sending without API key configured"""
        # Arrange
        email = "test@university.edu"
        otp_code = "123456"
        
        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            email_service.send_otp_email(email, otp_code)
        
        assert "Email service not configured" in str(exc_info.value)
    
    @patch('app.core.email.PostmarkClient')
    @patch('app.core.email.POSTMARK_API_KEY', 'test_postmark_api_key')
    def test_email_content_format(self, mock_client_class):
        """Test that email content is plain text only"""
        # Arrange
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.emails.send.return_value = {"MessageID": "test_email_id"}
        email = "test@university.edu"
        otp_code = "999888"
        
        # Act
        email_service.send_otp_email(email, otp_code)
        
        # Assert
        call_kwargs = mock_client.emails.send.call_args[1]
        # Verify plain text format
        assert "TextBody" in call_kwargs
        assert "HtmlBody" not in call_kwargs
        # Verify no links in content
        assert "http" not in call_kwargs["TextBody"]
        assert "https" not in call_kwargs["TextBody"]
