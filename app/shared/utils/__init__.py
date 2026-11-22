"""
Shared Utilities

Helper functions used across the application.

NO BUSINESS LOGIC - Structure only
"""

from typing import Optional
from datetime import datetime, timedelta
import re


# ================================
# EMAIL UTILITIES
# ================================

def validate_email_format(email: str) -> bool:
    """
    Validate email format using regex
    
    Args:
        email: Email address to validate
        
    Returns:
        True if email format is valid
    """
    # TODO: Implement email format validation
    pass


def extract_email_domain(email: str) -> str:
    """
    Extract domain from email address
    
    Args:
        email: Email address
        
    Returns:
        Domain part of email (e.g., "university.edu")
    """
    # TODO: Extract and return domain
    pass


def is_university_email(email: str, allowed_domains: list) -> bool:
    """
    Check if email is from allowed university domain
    
    Args:
        email: Email address to check
        allowed_domains: List of allowed domains
        
    Returns:
        True if email domain is allowed
    """
    # TODO: Check if email domain is in allowed list
    pass


# ================================
# STRING UTILITIES
# ================================

def generate_random_code(length: int = 6) -> str:
    """
    Generate random alphanumeric code
    
    Args:
        length: Length of code to generate
        
    Returns:
        Random code string
    """
    # TODO: Generate random code (for OTP, referral codes, etc.)
    pass


def sanitize_string(text: str) -> str:
    """
    Sanitize user input string
    
    Args:
        text: Input string
        
    Returns:
        Sanitized string
    """
    # TODO: Remove potentially harmful characters
    pass


# ================================
# DATE/TIME UTILITIES
# ================================

def utc_now() -> datetime:
    """Get current UTC datetime"""
    return datetime.utcnow()


def add_minutes(dt: datetime, minutes: int) -> datetime:
    """
    Add minutes to datetime
    
    Args:
        dt: Base datetime
        minutes: Minutes to add
        
    Returns:
        New datetime
    """
    return dt + timedelta(minutes=minutes)


def is_expired(expiry_time: datetime) -> bool:
    """
    Check if datetime has expired
    
    Args:
        expiry_time: Expiry datetime to check
        
    Returns:
        True if expired
    """
    return datetime.utcnow() > expiry_time


# ================================
# VALIDATION UTILITIES
# ================================

def validate_uuid(uuid_string: str) -> bool:
    """
    Validate UUID format
    
    Args:
        uuid_string: String to validate
        
    Returns:
        True if valid UUID
    """
    # TODO: Validate UUID format
    pass


# ================================
# PAGINATION UTILITIES
# ================================

def calculate_total_pages(total_items: int, page_size: int) -> int:
    """
    Calculate total number of pages
    
    Args:
        total_items: Total number of items
        page_size: Items per page
        
    Returns:
        Total number of pages
    """
    return (total_items + page_size - 1) // page_size


def calculate_skip(page: int, page_size: int) -> int:
    """
    Calculate number of items to skip for pagination
    
    Args:
        page: Page number (1-indexed)
        page_size: Items per page
        
    Returns:
        Number of items to skip
    """
    return (page - 1) * page_size
