"""
Integration tests for auth service with email delivery
"""

import pytest
from unittest.mock import patch, MagicMock
from app.modules.auth.service import auth_service


class TestAuthServiceEmailIntegration:
    """Test auth service email integration"""
    
    @pytest.mark.asyncio
    @patch('app.modules.auth.service.email_service.send_otp_email')
    @patch('app.modules.auth.service.redis_manager')
    @patch('app.modules.auth.service.get_supabase_client')
    async def test_send_otp_calls_email_service(
        self, 
        mock_supabase, 
        mock_redis, 
        mock_email_service
    ):
        """Test that send_otp calls email service instead of logging"""
        # Arrange
        email = "test@uowmail.edu.au"
        
        # Mock Supabase domain check
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [{"domain": "uowmail.edu.au", "is_active": True}]
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_result
        mock_supabase.return_value = mock_client
        
        # Mock Redis
        mock_redis.setex.return_value = True
        
        # Mock email service
        mock_email_service.return_value = True
        
        # Act
        result = await auth_service.send_otp(email)
        
        # Assert
        assert result == {"message": "OTP sent"}
        mock_email_service.assert_called_once()
        # Verify email was called with correct parameters
        call_args = mock_email_service.call_args
        assert call_args[0][0] == email  # First arg is email
        assert len(call_args[0][1]) == 6  # Second arg is 6-digit OTP
        assert call_args[1]["expiry_minutes"] == 5  # Keyword arg
    
    @pytest.mark.asyncio
    @patch('app.modules.auth.service.email_service.send_otp_email')
    @patch('app.modules.auth.service.redis_manager')
    @patch('app.modules.auth.service.get_supabase_client')
    @patch('builtins.print')
    async def test_otp_not_logged_to_console(
        self,
        mock_print,
        mock_supabase,
        mock_redis,
        mock_email_service
    ):
        """Test that OTP is NOT logged to console anymore"""
        # Arrange
        email = "test@uowmail.edu.au"
        
        # Mock Supabase domain check
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [{"domain": "uowmail.edu.au", "is_active": True}]
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_result
        mock_supabase.return_value = mock_client
        
        # Mock Redis
        mock_redis.setex.return_value = True
        
        # Mock email service
        mock_email_service.return_value = True
        
        # Act
        await auth_service.send_otp(email)
        
        # Assert - print should NOT be called with OTP
        mock_print.assert_not_called()
    
    @pytest.mark.asyncio
    @patch('app.modules.auth.service.email_service.send_otp_email')
    @patch('app.modules.auth.service.redis_manager')
    @patch('app.modules.auth.service.get_supabase_client')
    async def test_redis_key_namespacing(
        self,
        mock_supabase,
        mock_redis,
        mock_email_service
    ):
        """Test that Redis keys use proper namespacing"""
        # Arrange
        email = "test@uowmail.edu.au"
        
        # Mock Supabase domain check
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [{"domain": "uowmail.edu.au", "is_active": True}]
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_result
        mock_supabase.return_value = mock_client
        
        # Mock Redis
        mock_redis.setex.return_value = True
        
        # Mock email service
        mock_email_service.return_value = True
        
        # Act
        await auth_service.send_otp(email)
        
        # Assert - Redis key should use proper namespace
        mock_redis.setex.assert_called_once()
        redis_key = mock_redis.setex.call_args[0][0]
        assert redis_key == f"sv:app:auth:otp:{email}"
        assert mock_redis.setex.call_args[0][1] == 300  # TTL is 300 seconds
    
    @pytest.mark.asyncio
    @patch('app.modules.auth.service.email_service.send_otp_email')
    @patch('app.modules.auth.service.redis_manager')
    @patch('app.modules.auth.service.get_supabase_client')
    async def test_otp_deleted_on_email_failure(
        self,
        mock_supabase,
        mock_redis,
        mock_email_service
    ):
        """Test that OTP is deleted from Redis if email sending fails"""
        # Arrange
        email = "test@uowmail.edu.au"
        
        # Mock Supabase domain check
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [{"domain": "uowmail.edu.au", "is_active": True}]
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_result
        mock_supabase.return_value = mock_client
        
        # Mock Redis
        mock_redis.setex.return_value = True
        
        # Mock email service to fail
        mock_email_service.side_effect = Exception("Email service error")
        
        # Act & Assert
        with pytest.raises(Exception):
            await auth_service.send_otp(email)
        
        # Verify OTP was deleted from Redis
        mock_redis.delete.assert_called_once()
        redis_key = mock_redis.delete.call_args[0][0]
        assert redis_key == f"sv:app:auth:otp:{email}"
