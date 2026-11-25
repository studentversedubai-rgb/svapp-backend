import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()
dsn = os.getenv("DATABASE_URL")
conn = psycopg2.connect(dsn)
cur = conn.cursor(cursor_factory=RealDictCursor)

cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'users' ORDER BY column_name")
cols = [r["column_name"] for r in cur.fetchall()]
print(f"Users table has {len(cols)} columns:")
print("password_hash exists:", "password_hash" in cols)

if "password_hash" not in cols:
    print("Applying migration add_password_hash.sql...")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_personal_email ON users (personal_email);")
    conn.commit()
    print("Migration applied successfully!")

conn.close()
