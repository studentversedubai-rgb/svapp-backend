"""
Database Module

Manages connection to Supabase.
"""

import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

class DatabaseManager:
    """
    Manages database connections (Supabase)
    """
    
    def __init__(self):
        """Initialize database connections"""
        self.supabase: Client = None
        
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
        
        if not supabase_url or not supabase_key:
            print("WARNING: SUPABASE_URL or SUPABASE_KEY not found in environment")
            return
            
        try:
            self.supabase = create_client(supabase_url, supabase_key)
            print("INFO: Initialized Supabase client")
        except Exception as e:
            print(f"ERROR: Failed to initialize Supabase client: {e}")

# Global database manager instance
db_manager = DatabaseManager()

def get_supabase_client() -> Client:
    """Get Supabase client instance"""
    return db_manager.supabase
