"""
Configuration Management

Loads environment variables and provides application settings.
Uses Pydantic Settings for type-safe configuration.

NO BUSINESS LOGIC - Structure only
"""

from pydantic_settings import BaseSettings
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
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_KEY: str
    
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
    # CORS
    # ================================
    ALLOWED_ORIGINS: str = "http://localhost:3000"
    
    @property
    def allowed_origins_list(self) -> List[str]:
        """Parse comma-separated origins into list"""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]
    
    # ================================
    # RATE LIMITING
    # ================================
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60
    
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
    # SV ORBIT (Placeholder)
    # ================================
    # OPENAI_API_KEY: str = ""
    # ORBIT_MAX_RESULTS: int = 10
    
    # ================================
    # SV PAY (Placeholder)
    # ================================
    # STRIPE_SECRET_KEY: str = ""
    # STRIPE_WEBHOOK_SECRET: str = ""
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
# TODO: Initialize this properly in main.py
# settings = Settings()
