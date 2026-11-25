import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()
dsn = os.getenv("DATABASE_URL")
print("Target host:", dsn.split("@")[-1] if dsn else "None")

try:
    conn = psycopg2.connect(dsn)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
    tables = [r["table_name"] for r in cur.fetchall()]
    print(f"SUCCESS! Connected to Azure PostgreSQL. Found {len(tables)} tables:")
    for t in tables:
        print("  -", t)
    conn.close()
except Exception as e:
    print("DB Connection failed:", type(e).__name__, e)
