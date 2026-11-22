-- Migration: Add merchant_id to online_deals
-- This allows online deals to be associated with merchants like regular offers

-- Add merchant_id column
ALTER TABLE online_deals 
ADD COLUMN IF NOT EXISTS merchant_id UUID REFERENCES merchants(id);

-- Create index for faster joins
CREATE INDEX IF NOT EXISTS idx_online_deals_merchant_id ON online_deals(merchant_id);

-- Update existing online deals to have a merchant (optional - for existing data)
-- If you have existing online deals, you may want to assign them to a default merchant
-- UPDATE online_deals SET merchant_id = 'your-default-merchant-uuid' WHERE merchant_id IS NULL;

-- Note: After running this migration, update your backend code to:
-- 1. Require merchant_id when creating online deals
-- 2. Join with merchants table when fetching online deals
-- 3. Return merchant data in the response
