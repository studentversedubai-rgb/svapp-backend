"""
SV Pay Issuer Abstraction

Abstraction layer for payment service providers (PSP) / card issuers.
Allows switching between different payment providers.

NO BUSINESS LOGIC - Structure only
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional


class PaymentIssuerInterface(ABC):
    """
    Abstract interface for payment providers
    
    Implement this interface for each PSP:
    - Stripe
    - PayPal
    - Local payment gateways
    - Card issuers
    """
    
    @abstractmethod
    async def create_payment(
        self,
        amount: float,
        currency: str,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """
        Create payment with provider
        
        Args:
            amount: Payment amount
            currency: Currency code
            metadata: Additional data
            
        Returns:
            Payment creation response
        """
        pass
    
    @abstractmethod
    async def get_payment_status(self, payment_id: str) -> str:
        """
        Get payment status from provider
        
        Args:
            payment_id: Provider's payment ID
            
        Returns:
            Payment status
        """
        pass
    
    @abstractmethod
    async def cancel_payment(self, payment_id: str) -> bool:
        """
        Cancel payment
        
        Args:
            payment_id: Provider's payment ID
            
        Returns:
            True if cancelled successfully
        """
        pass
    
    @abstractmethod
    async def refund_payment(
        self,
        payment_id: str,
        amount: Optional[float] = None
    ) -> Dict:
        """
        Refund payment
        
        Args:
            payment_id: Provider's payment ID
            amount: Refund amount (None for full refund)
            
        Returns:
            Refund response
        """
        pass
    
    @abstractmethod
    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str
    ) -> bool:
        """
        Verify webhook signature
        
        Args:
            payload: Webhook payload
            signature: Signature from provider
            
        Returns:
            True if signature is valid
        """
        pass


class StripeIssuer(PaymentIssuerInterface):
    """
    Stripe payment provider implementation
    
    TODO: Implement all abstract methods
    """
    
    def __init__(self, api_key: str):
        """Initialize Stripe client"""
        # TODO: Initialize Stripe SDK
        pass
    
    async def create_payment(self, amount: float, currency: str, metadata: Optional[Dict] = None) -> Dict:
        # TODO: Implement Stripe payment creation
        pass
    
    async def get_payment_status(self, payment_id: str) -> str:
        # TODO: Implement Stripe status check
        pass
    
    async def cancel_payment(self, payment_id: str) -> bool:
        # TODO: Implement Stripe cancellation
        pass
    
    async def refund_payment(self, payment_id: str, amount: Optional[float] = None) -> Dict:
        # TODO: Implement Stripe refund
        pass
    
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        # TODO: Implement Stripe webhook verification
        pass


# TODO: Add other issuer implementations as needed
# class PayPalIssuer(PaymentIssuerInterface):
#     ...
