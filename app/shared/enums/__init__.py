"""
Shared Enums

Application-wide enumerations for type safety.

NO BUSINESS LOGIC - Structure only
"""

from enum import Enum


class UserRole(str, Enum):
    """User roles in the system"""
    STUDENT = "student"
    VALIDATOR = "validator"
    ADMIN = "admin"


class UserStatus(str, Enum):
    """User account status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"


class EntitlementState(str, Enum):
    """
    Entitlement lifecycle states
    Managed by state machine in entitlements module
    """
    AVAILABLE = "available"
    CLAIMED = "claimed"
    RESERVED = "reserved"
    REDEEMED = "redeemed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class OfferCategory(str, Enum):
    """Offer categories"""
    FOOD_BEVERAGE = "food_beverage"
    ENTERTAINMENT = "entertainment"
    RETAIL = "retail"
    SERVICES = "services"
    EDUCATION = "education"
    HEALTH_FITNESS = "health_fitness"
    TRAVEL = "travel"
    OTHER = "other"


class OfferType(str, Enum):
    """Types of offers"""
    DISCOUNT = "discount"
    FREEBIE = "freebie"
    BUNDLE = "bundle"
    CASHBACK = "cashback"


class RedemptionMethod(str, Enum):
    """How an entitlement is redeemed"""
    QR_CODE = "qr_code"
    CODE = "code"
    IN_APP = "in_app"
    VALIDATOR_SCAN = "validator_scan"


class PaymentStatus(str, Enum):
    """
    Payment transaction status
    Used by SV Pay module (feature flagged)
    """
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class AnalyticsEventType(str, Enum):
    """Analytics event types"""
    OFFER_VIEW = "offer_view"
    OFFER_CLAIM = "offer_claim"
    ENTITLEMENT_REDEEM = "entitlement_redeem"
    USER_LOGIN = "user_login"
    USER_SIGNUP = "user_signup"
    ORBIT_PLAN_GENERATE = "orbit_plan_generate"
    ORBIT_PLAN_VIEW = "orbit_plan_view"
    PAYMENT_INITIATED = "payment_initiated"
    PAYMENT_COMPLETED = "payment_completed"


class OrbitPlanStatus(str, Enum):
    """
    SV Orbit plan status
    """
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"
