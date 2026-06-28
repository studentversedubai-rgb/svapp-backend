"""
Offers Models - Phase 2

Database models for merchants, offers, and categories.
Implements time-based and day-based validity rules.

NOTE: Using Supabase directly, not SQLAlchemy ORM.
These are just reference schemas for the database tables.
"""

# Database schema reference (create these tables in Supabase):

# CREATE TABLE merchants (
#   id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
#   name VARCHAR NOT NULL,
#   description TEXT,
#   logo_url VARCHAR,
#   latitude FLOAT,
#   longitude FLOAT,
#   address TEXT,
#   is_active BOOLEAN DEFAULT TRUE,
#   created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
#   updated_at TIMESTAMP WITH TIME ZONE
# );

# CREATE TABLE categories (
#   id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
#   name VARCHAR UNIQUE NOT NULL,
#   slug VARCHAR UNIQUE NOT NULL,
#   description TEXT,
#   icon_url VARCHAR,
#   sort_order INTEGER DEFAULT 0,
#   is_active BOOLEAN DEFAULT TRUE,
#   created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
# );

# CREATE TABLE offers (
#   id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
#   merchant_id UUID REFERENCES merchants(id),
#   category_id UUID REFERENCES categories(id),
#   title VARCHAR NOT NULL,
#   description TEXT NOT NULL,
#   terms_conditions TEXT,
#   offer_type VARCHAR NOT NULL,
#   discount_value VARCHAR,
#   original_price FLOAT,
#   discounted_price FLOAT,
#   image_url VARCHAR,
#   images TEXT[],
#   valid_from TIMESTAMP WITH TIME ZONE NOT NULL,
#   valid_until TIMESTAMP WITH TIME ZONE NOT NULL,
#   time_valid_from TIME,
#   time_valid_until TIME,
#   valid_days_of_week INTEGER[],
#   max_claims_per_user INTEGER,
#   total_claims INTEGER DEFAULT 0,
#   max_total_claims INTEGER,
#   is_active BOOLEAN DEFAULT TRUE,
#   is_featured BOOLEAN DEFAULT FALSE,
#   created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
#   updated_at TIMESTAMP WITH TIME ZONE
# );

# CREATE INDEX idx_offers_merchant_id ON offers(merchant_id);
# CREATE INDEX idx_offers_category_id ON offers(category_id);
# CREATE INDEX idx_offers_is_active ON offers(is_active);
# CREATE INDEX idx_offers_valid_from ON offers(valid_from);
# CREATE INDEX idx_offers_valid_until ON offers(valid_until);
# CREATE INDEX idx_offers_created_at ON offers(created_at);
# CREATE INDEX idx_merchants_is_active ON merchants(is_active);
