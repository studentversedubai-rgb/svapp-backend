"""
Users Models

SQLAlchemy models for users table.

NO BUSINESS LOGIC - Structure only
"""

# from sqlalchemy import Column, String, DateTime, Integer, Enum
# from sqlalchemy.sql import func
# from app.core.database import Base
# from app.shared.enums import UserRole, UserStatus


# class User(Base):
#     """User model"""
#     __tablename__ = "users"
#     
#     id = Column(String, primary_key=True)  # UUID from Supabase
#     email = Column(String, unique=True, nullable=False, index=True)  # IMMUTABLE
#     first_name = Column(String, nullable=True)
#     last_name = Column(String, nullable=True)
#     phone_number = Column(String, nullable=True)
#     university = Column(String, nullable=True)
#     graduation_year = Column(Integer, nullable=True)
#     role = Column(Enum(UserRole), default=UserRole.STUDENT, nullable=False)
#     status = Column(Enum(UserStatus), default=UserStatus.ACTIVE, nullable=False)
#     created_at = Column(DateTime(timezone=True), server_default=func.now())
#     updated_at = Column(DateTime(timezone=True), onupdate=func.now())
#     last_login = Column(DateTime(timezone=True), nullable=True)

# TODO: Define User model with SQLAlchemy
# TODO: Add indexes for performance
# TODO: Add relationships to other tables
