"""
Users Service

Business logic for user management.

NO BUSINESS LOGIC - Structure only
"""

# from app.modules.users.schemas import UserProfile, UpdateUserRequest, CreateUserInternal
# from app.core.database import get_db_session


class UserService:
    """Handles user operations"""
    
    async def get_user_by_id(self, user_id: str) -> dict:
        """
        Get user by ID
        
        Args:
            user_id: User UUID
            
        Returns:
            User profile data
        """
        # TODO: Query database for user
        pass
    
    async def get_user_by_email(self, email: str) -> dict:
        """
        Get user by email
        
        Args:
            email: User email
            
        Returns:
            User profile data or None
        """
        # TODO: Query database for user by email
        pass
    
    async def create_user(self, user_data: dict) -> dict:
        """
        Create new user (called by auth module)
        
        Args:
            user_data: User creation data
            
        Returns:
            Created user profile
        """
        # TODO: Insert user into database
        pass
    
    async def update_user(self, user_id: str, update_data: dict) -> dict:
        """
        Update user profile
        
        IMPORTANT: Email cannot be updated
        
        Args:
            user_id: User UUID
            update_data: Fields to update
            
        Returns:
            Updated user profile
        """
        # TODO: Update user in database
        # TODO: Ensure email is not in update_data
        pass
    
    async def update_last_login(self, user_id: str):
        """
        Update user's last login timestamp
        
        Args:
            user_id: User UUID
        """
        # TODO: Update last_login field
        pass
