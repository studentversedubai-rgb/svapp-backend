"""
Entitlements Models - Phase 3

Database table schemas for entitlements and redemptions.
These are reference schemas for Supabase tables.

IMPORTANT: Create these tables in Supabase before using.
"""

# ================================
# ENTITLEMENTS TABLE
# ================================

# CREATE TABLE entitlements (
#   id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
#   user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
#   offer_id UUID NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
#   device_id VARCHAR,  -- Device binding for fraud prevention
#   
#   -- State management
#   state VARCHAR NOT NULL DEFAULT 'active',  -- active, pending_confirmation, used, voided, expired
#   
#   -- Timestamps
#   claimed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
#   expires_at TIMESTAMP WITH TIME ZONE NOT NULL,  -- End of day
#   used_at TIMESTAMP WITH TIME ZONE,
#   voided_at TIMESTAMP WITH TIME ZONE,
#   
#   -- Metadata
#   created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
#   updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
#   
#   -- Constraints
#   CONSTRAINT valid_state CHECK (state IN ('active', 'pending_confirmation', 'used', 'voided', 'expired'))
# );

# -- Indexes for performance
# CREATE INDEX idx_entitlements_user_id ON entitlements(user_id);
# CREATE INDEX idx_entitlements_offer_id ON entitlements(offer_id);
# CREATE INDEX idx_entitlements_state ON entitlements(state);
# CREATE INDEX idx_entitlements_claimed_at ON entitlements(claimed_at);
# CREATE INDEX idx_entitlements_expires_at ON entitlements(expires_at);

# -- Composite index for daily usage enforcement
# CREATE UNIQUE INDEX idx_entitlements_user_offer_day ON entitlements(
#   user_id, 
#   offer_id, 
#   DATE(claimed_at)
# ) WHERE state != 'voided';  -- Voided entitlements don't count


# ================================
# REDEMPTIONS TABLE
# ================================

# CREATE TABLE redemptions (
#   id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
#   entitlement_id UUID NOT NULL REFERENCES entitlements(id) ON DELETE CASCADE,
#   
#   -- Merchant & Offer Info
#   merchant_id UUID NOT NULL REFERENCES merchants(id),
#   offer_id UUID NOT NULL REFERENCES offers(id),
#   user_id UUID NOT NULL REFERENCES auth.users(id),
#   
#   -- Financial Data
#   total_bill_amount DECIMAL(10, 2) NOT NULL,
#   discount_amount DECIMAL(10, 2) NOT NULL,
#   final_amount DECIMAL(10, 2) NOT NULL,
#   
#   -- Offer Type (for analytics)
#   offer_type VARCHAR NOT NULL,  -- percentage, bogo, bundle
#   
#   -- Timestamps
#   redeemed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
#   
#   -- Void tracking
#   is_voided BOOLEAN DEFAULT FALSE,
#   voided_at TIMESTAMP WITH TIME ZONE,
#   void_reason TEXT,
#   
#   -- Metadata
#   created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
#   updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
# );

# -- Indexes for analytics and reporting
# CREATE INDEX idx_redemptions_entitlement_id ON redemptions(entitlement_id);
# CREATE INDEX idx_redemptions_merchant_id ON redemptions(merchant_id);
# CREATE INDEX idx_redemptions_offer_id ON redemptions(offer_id);
# CREATE INDEX idx_redemptions_user_id ON redemptions(user_id);
# CREATE INDEX idx_redemptions_redeemed_at ON redemptions(redeemed_at);
# CREATE INDEX idx_redemptions_is_voided ON redemptions(is_voided);


# ================================
# ANALYTICS VIEW (Optional)
# ================================

# CREATE VIEW redemption_analytics AS
# SELECT 
#   r.merchant_id,
#   r.offer_id,
#   r.user_id,
#   DATE(r.redeemed_at) as redemption_date,
#   COUNT(*) as redemption_count,
#   SUM(r.total_bill_amount) as total_revenue,
#   SUM(r.discount_amount) as total_savings,
#   SUM(r.final_amount) as net_revenue
# FROM redemptions r
# WHERE r.is_voided = FALSE
# GROUP BY r.merchant_id, r.offer_id, r.user_id, DATE(r.redeemed_at);


# ================================
# RLS POLICIES (Row Level Security)
# ================================

# -- Enable RLS
# ALTER TABLE entitlements ENABLE ROW LEVEL SECURITY;
# ALTER TABLE redemptions ENABLE ROW LEVEL SECURITY;

# -- Students can only see their own entitlements
# CREATE POLICY "Users can view own entitlements" ON entitlements
#   FOR SELECT
#   USING (auth.uid() = user_id);

# -- Students can only see their own redemptions
# CREATE POLICY "Users can view own redemptions" ON redemptions
#   FOR SELECT
#   USING (auth.uid() = user_id);

# -- Service role can do everything (for backend operations)
# CREATE POLICY "Service role full access entitlements" ON entitlements
#   FOR ALL
#   USING (auth.role() = 'service_role');

# CREATE POLICY "Service role full access redemptions" ON redemptions
#   FOR ALL
#   USING (auth.role() = 'service_role');


# ================================
# FUNCTIONS FOR AUTOMATIC EXPIRY
# ================================

# -- Function to expire entitlements at end of day
# CREATE OR REPLACE FUNCTION expire_old_entitlements()
# RETURNS void AS $$
# BEGIN
#   UPDATE entitlements
#   SET state = 'expired', updated_at = NOW()
#   WHERE state IN ('active', 'pending_confirmation')
#     AND expires_at < NOW();
# END;
# $$ LANGUAGE plpgsql;

# -- Schedule this function to run periodically (use pg_cron or external scheduler)
