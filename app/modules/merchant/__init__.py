"""
Merchant Validation Module

Public endpoints for merchant-side QR validation and redemption.
Does NOT require student JWT authentication.
"""

from app.modules.merchant.router import router

__all__ = ['router']
