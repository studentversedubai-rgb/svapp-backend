"""
Security Module

Handles JWT verification with Supabase Auth.
"""

import logging
from typing import Optional, Dict
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.database import get_supabase_client

logger = logging.getLogger(__name__)

# Security scheme for JWT bearer tokens
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict:
    """
    Dependency to get current authenticated user from JWT
    
    Validates JWT with Supabase and fetches user from public.users
    
    Args:
        credentials: HTTP Authorization header with Bearer token
        
    Returns:
        User dict with id, email, name, etc.
        
    Raises:
        HTTPException: 401 if authentication fails
    """
    supabase = get_supabase_client()
    if not supabase:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database connection error"
        )
    
    token = credentials.credentials
    
    try:
        # Validate token with Supabase Auth
        auth_response = supabase.auth.get_user(token)
        
        if not auth_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        user_id = auth_response.user.id
        
        # Fetch user details from public.users
        try:
            user_result = supabase.table("users").select("*").eq("id", user_id).execute()
            
            if not user_result.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User profile not found"
                )
            
            return user_result.data[0]
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to fetch user profile: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve user data"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"}
        )
