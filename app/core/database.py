"""
Database Module

Manages connection to Supabase PostgreSQL database.
Uses both Supabase client and direct PostgreSQL connection.

NO BUSINESS LOGIC - Structure only
"""

from typing import AsyncGenerator
# from supabase import create_client, Client
# from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
# from sqlalchemy.orm import declarative_base
# from app.core.config import settings


# SQLAlchemy Base for ORM models
# Base = declarative_base()


class DatabaseManager:
    """
    Manages database connections and sessions
    """
    
    def __init__(self):
        """Initialize database connections"""
        # TODO: Create Supabase client
        # self.supabase: Client = create_client(
        #     settings.SUPABASE_URL,
        #     settings.SUPABASE_SERVICE_KEY
        # )
        
        # TODO: Create SQLAlchemy async engine for direct PostgreSQL access
        # self.engine = create_async_engine(
        #     settings.DATABASE_URL,  # Construct from Supabase connection string
        #     echo=settings.DEBUG,
        # )
        
        # TODO: Create session factory
        # self.async_session = async_sessionmaker(
        #     self.engine,
        #     class_=AsyncSession,
        #     expire_on_commit=False,
        # )
        
        pass
    
    async def init_db(self):
        """
        Initialize database
        Create tables if they don't exist
        """
        # TODO: Create all tables from Base metadata
        # async with self.engine.begin() as conn:
        #     await conn.run_sync(Base.metadata.create_all)
        
        pass
    
    async def close(self):
        """Close database connections"""
        # TODO: Dispose engine
        # await self.engine.dispose()
        
        pass


# Global database manager instance
# db_manager = DatabaseManager()


async def get_db_session() -> AsyncGenerator:
    """
    Dependency to get database session
    
    Usage in routes:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db_session)):
            # Use db session
            pass
    """
    # TODO: Create and yield session
    # async with db_manager.async_session() as session:
    #     try:
    #         yield session
    #         await session.commit()
    #     except Exception:
    #         await session.rollback()
    #         raise
    
    pass


def get_supabase_client():
    """
    Get Supabase client instance
    
    Usage:
        supabase = get_supabase_client()
        result = supabase.table('users').select('*').execute()
    """
    # TODO: Return Supabase client from db_manager
    pass


async def init_db():
    """Initialize database - called on startup"""
    # TODO: Call db_manager.init_db()
    pass
