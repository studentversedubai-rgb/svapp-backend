"""
Security Module

Handles JWT verification with Supabase Auth.
IMPORTANT: Passwords are NOT stored in this backend.
Supabase Auth handles all password management.

This module only VERIFIES JWTs issued by Supabase.

NO BUSINESS LOGIC - Structure only
"""

from typing import Optional
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
# from jose import JWTError, jwt
# from app.core.config import settings


# Security scheme for JWT bearer tokens
security = HTTPBearer()


class JWTVerifier:
    """
    Verifies JWT tokens issued by Supabase Auth
    Does NOT issue tokens - that's Supabase's job
    """
    
    @staticmethod
    def verify_token(token: str) -> dict:
        """
        Verify JWT token from Supabase
        
        Args:
            token: JWT token string
            
        Returns:
            Decoded token payload with user information
            
        Raises:
            HTTPException: If token is invalid or expired
        """
        # TODO: Implement JWT verification using python-jose
        # TODO: Verify signature using Supabase JWT secret
        # TODO: Check expiration
        # TODO: Extract user_id and email from payload
        
        pass
    
    @staticmethod
    def get_user_id_from_token(token: str) -> str:
        """
        Extract user ID from verified token
        
        Args:
            token: JWT token string
            
        Returns:
            User ID (UUID from Supabase Auth)
        """
        # TODO: Verify token and extract user_id
        pass


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> dict:
    """
    Dependency to get current authenticated user from JWT
    
    Usage in routes:
        @router.get("/me")
        async def get_me(user: dict = Depends(get_current_user)):
            return user
    
    Args:
        credentials: HTTP Authorization header with Bearer token
        
    Returns:
        User information from token
        
    Raises:
        HTTPException: If authentication fails
    """
    # TODO: Extract token from credentials
    # TODO: Verify token using JWTVerifier
    # TODO: Return user information
    
    pass


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> Optional[dict]:
    """
    Optional authentication dependency
    Returns None if no token provided, otherwise verifies token
    
    Useful for endpoints that work with or without authentication
    """
    # TODO: Implement optional authentication
    pass


def verify_university_email(email: str) -> bool:
    """
    Verify that email is from an allowed university domain
    
    Args:
        email: Email address to verify
        
    Returns:
        True if email domain is allowed
    """
    # TODO: Check email domain against ALLOWED_EMAIL_DOMAINS
    # TODO: Email must be immutable - this is checked during registration
    
    pass
