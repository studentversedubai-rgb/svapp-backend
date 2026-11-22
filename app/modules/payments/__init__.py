"""
Payments Module

Stripe payment processing and webhook handling for ticket bookings.
"""

from app.modules.payments.router import router

__all__ = ['router']
