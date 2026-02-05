"""
Shared Constants

Application-wide constants and configuration values.

NO BUSINESS LOGIC - Structure only
"""

# ================================
# API VERSIONING
# ================================
API_V1_PREFIX = "/api/v1"

# ================================
# PAGINATION
# ================================
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# ================================
# RATE LIMITING
# ================================
RATE_LIMIT_WINDOW_SECONDS = 60
DEFAULT_RATE_LIMIT = 60

# ================================
# JWT
# ================================
JWT_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
JWT_REFRESH_TOKEN_EXPIRE_DAYS = 30

# ================================
# OTP (if used)
# ================================
OTP_LENGTH = 6
OTP_EXPIRE_MINUTES = 10
OTP_MAX_ATTEMPTS = 3

# ================================
# EMAIL
# ================================
EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

# ================================
# ENTITLEMENTS & REDEMPTION - PHASE 3
# ================================
# QR Token Settings
QR_PROOF_TOKEN_TTL_SECONDS = 30  # Short-lived proof token (20-30s)
QR_TOKEN_LENGTH = 32  # Secure random token length

# Redemption Settings
VOID_WINDOW_HOURS = 2  # Void allowed within 2 hours
MAX_DAILY_CLAIMS_PER_OFFER = 1  # One entitlement per user per offer per day

# Redis Key Prefixes (Namespacing)
REDIS_PREFIX_QR_TOKEN = "sv:app:redeem:token:"  # QR proof tokens
REDIS_PREFIX_DAILY_CLAIM = "sv:app:claim:daily:"  # Daily usage tracking
REDIS_PREFIX_OTP = "sv:app:otp:"  # OTP storage (existing)

# ================================
# SV ORBIT
# ================================
# TODO: Define Orbit-specific constants
# ORBIT_MAX_PLAN_ITEMS = 10
# ORBIT_CACHE_TTL_SECONDS = 3600

# ================================
# SV PAY
# ================================
# TODO: Define payment-specific constants
# PAYMENT_STATUS_PENDING = "pending"
# PAYMENT_STATUS_COMPLETED = "completed"
# PAYMENT_STATUS_FAILED = "failed"
