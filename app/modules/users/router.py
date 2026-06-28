"""
Users Router

Manages user profiles and settings.
Email is IMMUTABLE - cannot be changed after registration.

Endpoints:
- GET /users/me: Get current user profile
- PATCH /users/me: Update user profile (not email)
- GET /users/{user_id}: Get user by ID (admin only)

NO BUSINESS LOGIC - Structure only
"""

from fastapi import APIRouter, Depends
# from app.core.security import get_current_user
# from app.modules.users.schemas import UserProfile, UpdateUserRequest
# from app.modules.users.service import UserService

router = APIRouter()


@router.get("/me")
async def get_current_user_profile():
    """
    Get current authenticated user's profile
    
    Returns:
        User profile data
    """
    # TODO: Implement get current user
    pass


@router.patch("/me")
async def update_current_user_profile():
    """
    Update current user's profile
    
    IMPORTANT: Email cannot be updated (immutable)
    
    Returns:
        Updated user profile
    """
    # TODO: Implement profile update
    # TODO: Ensure email cannot be changed
    pass


@router.get("/{user_id}")
async def get_user_by_id():
    """
    Get user by ID (admin only)
    
    Returns:
        User profile data
    """
    # TODO: Implement get user by ID
    # TODO: Add admin permission check
    pass
