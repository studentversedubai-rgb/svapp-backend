-- Add Stripe columns to ticket_records and users tables
ALTER TABLE public.ticket_records 
ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR,
ADD COLUMN IF NOT EXISTS payment_status VARCHAR;

-- We already have stripe_payment_intent_id but let's ensure it exists
ALTER TABLE public.ticket_records
ADD COLUMN IF NOT EXISTS stripe_payment_intent_id VARCHAR;

-- Update existing column if it is named stripe_payment_status to payment_status if preferred,
-- but adding payment_status is safer to match the exact instructions.

-- Add stripe_customer_id to users
ALTER TABLE public.users
ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR;