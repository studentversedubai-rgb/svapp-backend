"""
Entitlements Models

NO BUSINESS LOGIC - Structure only
"""

# from sqlalchemy import Column, String, DateTime, ForeignKey
# from sqlalchemy.sql import func
# from app.core.database import Base


# class Entitlement(Base):
#     """Entitlement model"""
#     __tablename__ = "entitlements"
#     
#     id = Column(String, primary_key=True)
#     user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
#     offer_id = Column(String, ForeignKey("offers.id"), nullable=False, index=True)
#     state = Column(String, nullable=False, index=True)
#     redemption_method = Column(String, nullable=False)
#     redemption_code = Column(String, nullable=True)
#     claimed_at = Column(DateTime(timezone=True), server_default=func.now())
#     reserved_at = Column(DateTime(timezone=True), nullable=True)
#     redeemed_at = Column(DateTime(timezone=True), nullable=True)
#     expires_at = Column(DateTime(timezone=True), nullable=True)
#     validator_id = Column(String, ForeignKey("users.id"), nullable=True)
#     notes = Column(String, nullable=True)
#     created_at = Column(DateTime(timezone=True), server_default=func.now())
#     updated_at = Column(DateTime(timezone=True), onupdate=func.now())

# TODO: Define Entitlement model
# TODO: Add relationships to User and Offer
# TODO: Add indexes for performance
