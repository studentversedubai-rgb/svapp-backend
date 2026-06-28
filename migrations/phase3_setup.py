"""
Phase 3 Database Migration Script

Creates entitlements and redemptions tables in Supabase.

Run this script to set up the database schema for Phase 3.

Usage:
    python migrations/phase3_setup.py
"""

import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()


def create_tables():
    """Create Phase 3 database tables"""
    
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    
    if not supabase_url or not supabase_key:
        print("ERROR: Missing SUPABASE_URL or SUPABASE_SERVICE_KEY")
        return False
    
    supabase = create_client(supabase_url, supabase_key)
    
    # SQL statements to create tables
    sql_statements = [
        # Create entitlements table
        """
        CREATE TABLE IF NOT EXISTS entitlements (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
            offer_id UUID NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
            device_id VARCHAR,
            
            state VARCHAR NOT NULL DEFAULT 'active',
            
            claimed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            used_at TIMESTAMP WITH TIME ZONE,
            voided_at TIMESTAMP WITH TIME ZONE,
            
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            
            CONSTRAINT valid_state CHECK (state IN ('active', 'pending_confirmation', 'used', 'voided', 'expired'))
        );
        """,
        
        # Create indexes for entitlements
        """
        CREATE INDEX IF NOT EXISTS idx_entitlements_user_id ON entitlements(user_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_entitlements_offer_id ON entitlements(offer_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_entitlements_state ON entitlements(state);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_entitlements_claimed_at ON entitlements(claimed_at);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_entitlements_expires_at ON entitlements(expires_at);
        """,
        
        # Create unique index for daily usage enforcement
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_entitlements_user_offer_day 
        ON entitlements(user_id, offer_id, DATE(claimed_at))
        WHERE state != 'voided';
        """,
        
        # Create redemptions table
        """
        CREATE TABLE IF NOT EXISTS redemptions (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            entitlement_id UUID NOT NULL REFERENCES entitlements(id) ON DELETE CASCADE,
            
            merchant_id UUID NOT NULL REFERENCES merchants(id),
            offer_id UUID NOT NULL REFERENCES offers(id),
            user_id UUID NOT NULL REFERENCES auth.users(id),
            
            total_bill_amount DECIMAL(10, 2) NOT NULL,
            discount_amount DECIMAL(10, 2) NOT NULL,
            final_amount DECIMAL(10, 2) NOT NULL,
            
            offer_type VARCHAR NOT NULL,
            
            redeemed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            
            is_voided BOOLEAN DEFAULT FALSE,
            voided_at TIMESTAMP WITH TIME ZONE,
            void_reason TEXT,
            
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """,
        
        # Create indexes for redemptions
        """
        CREATE INDEX IF NOT EXISTS idx_redemptions_entitlement_id ON redemptions(entitlement_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_redemptions_merchant_id ON redemptions(merchant_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_redemptions_offer_id ON redemptions(offer_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_redemptions_user_id ON redemptions(user_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_redemptions_redeemed_at ON redemptions(redeemed_at);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_redemptions_is_voided ON redemptions(is_voided);
        """,
        
        # Create analytics view
        """
        CREATE OR REPLACE VIEW redemption_analytics AS
        SELECT 
            r.merchant_id,
            r.offer_id,
            r.user_id,
            DATE(r.redeemed_at) as redemption_date,
            COUNT(*) as redemption_count,
            SUM(r.total_bill_amount) as total_revenue,
            SUM(r.discount_amount) as total_savings,
            SUM(r.final_amount) as net_revenue
        FROM redemptions r
        WHERE r.is_voided = FALSE
        GROUP BY r.merchant_id, r.offer_id, r.user_id, DATE(r.redeemed_at);
        """,
        
        # Enable RLS
        """
        ALTER TABLE entitlements ENABLE ROW LEVEL SECURITY;
        """,
        """
        ALTER TABLE redemptions ENABLE ROW LEVEL SECURITY;
        """,
        
        # RLS Policies for entitlements
        """
        DROP POLICY IF EXISTS "Users can view own entitlements" ON entitlements;
        """,
        """
        CREATE POLICY "Users can view own entitlements" ON entitlements
            FOR SELECT
            USING (auth.uid() = user_id);
        """,
        """
        DROP POLICY IF EXISTS "Service role full access entitlements" ON entitlements;
        """,
        """
        CREATE POLICY "Service role full access entitlements" ON entitlements
            FOR ALL
            USING (auth.role() = 'service_role');
        """,
        
        # RLS Policies for redemptions
        """
        DROP POLICY IF EXISTS "Users can view own redemptions" ON redemptions;
        """,
        """
        CREATE POLICY "Users can view own redemptions" ON redemptions
            FOR SELECT
            USING (auth.uid() = user_id);
        """,
        """
        DROP POLICY IF EXISTS "Service role full access redemptions" ON redemptions;
        """,
        """
        CREATE POLICY "Service role full access redemptions" ON redemptions
            FOR ALL
            USING (auth.role() = 'service_role');
        """,
        
        # Function to expire old entitlements
        """
        CREATE OR REPLACE FUNCTION expire_old_entitlements()
        RETURNS void AS $$
        BEGIN
            UPDATE entitlements
            SET state = 'expired', updated_at = NOW()
            WHERE state IN ('active', 'pending_confirmation')
                AND expires_at < NOW();
        END;
        $$ LANGUAGE plpgsql;
        """,
        
        # Create analytics_events table if not exists
        """
        CREATE TABLE IF NOT EXISTS analytics_events (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            event_type VARCHAR NOT NULL,
            event_data JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_analytics_events_type ON analytics_events(event_type);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_analytics_events_created_at ON analytics_events(created_at);
        """
    ]
    
    print("Creating Phase 3 database tables...")
    
    # Execute SQL statements using Supabase RPC
    # Note: Supabase Python client doesn't support raw SQL execution directly
    # You'll need to run these via Supabase SQL Editor or use psycopg2
    
    print("\n" + "="*60)
    print("IMPORTANT: Run the following SQL in Supabase SQL Editor")
    print("="*60 + "\n")
    
    for i, sql in enumerate(sql_statements, 1):
        print(f"-- Statement {i}")
        print(sql.strip())
        print()
    
    print("="*60)
    print("\nAlternatively, copy all statements and run them at once.")
    print("="*60)
    
    return True


if __name__ == "__main__":
    print("Phase 3 Database Setup")
    print("=" * 60)
    
    success = create_tables()
    
    if success:
        print("\n✓ Migration SQL generated successfully")
        print("\nNext steps:")
        print("1. Copy the SQL statements above")
        print("2. Go to Supabase Dashboard > SQL Editor")
        print("3. Paste and run the SQL")
        print("4. Verify tables are created")
    else:
        print("\n✗ Migration failed")
