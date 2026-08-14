"""
Configuration Management

Loads environment variables and provides application settings.
Uses Pydantic Settings for type-safe configuration.

NO BUSINESS LOGIC - Structure only
"""

from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables
    """
    
    # ================================
    # APPLICATION
    # ================================
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    API_VERSION: str = "v1"
    PORT: int = 8000
    
    # ================================
    # SUPABASE
    # ================================
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_KEY: str
    VERIFICATION_BUCKET_NAME: str = "user-verification-documents"
    
    # ================================
    # JWT
    # ================================
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    
    # ================================
    # REDIS
    # ================================
    REDIS_URL: str
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0
    
    # ================================
    # RATE LIMITING
    # ================================
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60
    MAX_UPLOAD_SIZE_BYTES: int = 26214400
    VERIFICATION_FILE_MAX_BYTES: int = 10485760
    
    # ================================
    # EMAIL VALIDATION
    # ================================
    ALLOWED_EMAIL_DOMAINS: str = "student.university.edu"
    
    @property
    def allowed_email_domains_list(self) -> List[str]:
        """Parse comma-separated domains into list"""
        return [domain.strip() for domain in self.ALLOWED_EMAIL_DOMAINS.split(",")]
    
    # ================================
    # FEATURE FLAGS
    # ================================
    FEATURE_SV_PAY_ENABLED: bool = False
    FEATURE_SV_ORBIT_ENABLED: bool = True
    FEATURE_ANALYTICS_ENABLED: bool = True
    
    # ================================
    # EMAIL SERVICE (RESEND)
    # ================================
    RESEND_API_KEY: str = ""
    RESEND_FROM: str = "auth@loginotp.studentverse.app"
    POSTMARK_API_KEY: str = ""
    REVIEW_FROM_ADDRESS: str = "register@studentverse.app"
    
    # ================================
    # SV ORBIT
    # ================================
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "google/gemini-2.0-flash-001"
    ORBIT_MAX_RESULTS: int = 10
    
    # Rate limiting for Orbit chat
    DAILY_CHAT_LIMIT: int = 150  # Max chat requests per 24 hours
    VELOCITY_LIMIT: int = 10  # Max requests per minute
    VELOCITY_WINDOW: int = 60  # Velocity window in seconds
    
    # ================================
    # SV PAY
    # ================================
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # ================================
    # INTERNAL ADMIN API
    # ================================
    ADMIN_API_TOKEN: str = ""
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """
    Get application settings using LRU cache for performance.
    Settings are loaded only once on first call.
    """
    return Settings()

settings = get_settings()