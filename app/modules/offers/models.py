"""
Offers Models

NO BUSINESS LOGIC - Structure only
"""

# from sqlalchemy import Column, String, DateTime, Boolean, Integer, Text
# from sqlalchemy.sql import func
# from app.core.database import Base


# class Offer(Base):
#     """Offer model"""
#     __tablename__ = "offers"
#     
#     id = Column(String, primary_key=True)
#     partner_id = Column(String, nullable=False, index=True)
#     partner_name = Column(String, nullable=False)
#     title = Column(String, nullable=False)
#     description = Column(Text, nullable=False)
#     category = Column(String, nullable=False)
#     offer_type = Column(String, nullable=False)
#     discount_value = Column(String, nullable=True)
#     terms_conditions = Column(Text, nullable=False)
#     valid_from = Column(DateTime(timezone=True), nullable=False)
#     valid_until = Column(DateTime(timezone=True), nullable=False)
#     image_url = Column(String, nullable=True)
#     is_active = Column(Boolean, default=True)
#     max_claims_per_user = Column(Integer, nullable=True)
#     total_claims = Column(Integer, default=0)
#     created_at = Column(DateTime(timezone=True), server_default=func.now())
#     updated_at = Column(DateTime(timezone=True), onupdate=func.now())

# TODO: Define Offer model
