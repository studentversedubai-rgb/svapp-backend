"""
Base Pydantic Schemas

Shared base models and common response schemas.

NO BUSINESS LOGIC - Structure only
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Generic, TypeVar, List
from datetime import datetime


# ================================
# BASE MODELS
# ================================

class BaseSchema(BaseModel):
    """Base schema with common configuration"""
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )


class TimestampMixin(BaseModel):
    """Mixin for created_at and updated_at timestamps"""
    created_at: datetime
    updated_at: datetime


class IDMixin(BaseModel):
    """Mixin for ID field"""
    id: str = Field(..., description="Unique identifier (UUID)")


# ================================
# RESPONSE MODELS
# ================================

T = TypeVar('T')


class SuccessResponse(BaseSchema, Generic[T]):
    """
    Standard success response wrapper
    
    Usage:
        return SuccessResponse(
            success=True,
            message="Operation successful",
            data=user_data
        )
    """
    success: bool = True
    message: str
    data: Optional[T] = None


class ErrorResponse(BaseSchema):
    """
    Standard error response
    
    Usage:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                success=False,
                error="Invalid input",
                details={"field": "email", "issue": "Invalid format"}
            ).model_dump()
        )
    """
    success: bool = False
    error: str
    details: Optional[dict] = None


class PaginatedResponse(BaseSchema, Generic[T]):
    """
    Paginated response wrapper
    
    Usage:
        return PaginatedResponse(
            items=users,
            total=100,
            page=1,
            page_size=20,
            total_pages=5
        )
    """
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int


# ================================
# REQUEST MODELS
# ================================

class PaginationParams(BaseSchema):
    """
    Standard pagination parameters
    
    Usage as dependency:
        @router.get("/items")
        async def get_items(pagination: PaginationParams = Depends()):
            skip = (pagination.page - 1) * pagination.page_size
            limit = pagination.page_size
    """
    page: int = Field(1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(20, ge=1, le=100, description="Items per page")


# ================================
# HEALTH CHECK
# ================================

class HealthCheckResponse(BaseSchema):
    """Health check response"""
    status: str
    service: str
    version: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
