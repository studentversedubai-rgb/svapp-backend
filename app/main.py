"""
StudentVerse Backend - FastAPI Application Entry Point

This is the main application file that initializes FastAPI,
registers all routers, and configures middleware.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.redis import redis_manager
from app.modules.auth.router import router as auth_router
from app.modules.offers.router import router as offers_router

def create_app() -> FastAPI:
    """
    Application factory pattern
    Creates and configures the FastAPI application instance
    """
    
    app = FastAPI(
        title="StudentVerse API",
        description="Backend API for StudentVerse mobile application",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        swagger_ui_parameters={
            "persistAuthorization": True
        }
    )
    
    # Add security scheme for Swagger UI
    from fastapi.openapi.utils import get_openapi
    
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        openapi_schema = get_openapi(
            title="StudentVerse API",
            version="1.0.0",
            description="Backend API for StudentVerse mobile application",
            routes=app.routes,
        )
        openapi_schema["components"]["securitySchemes"] = {
            "HTTPBearer": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT"
            }
        }
        app.openapi_schema = openapi_schema
        return app.openapi_schema
    
    app.openapi = custom_openapi
    
    # ================================
    # CORS Configuration
    # ================================
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # ================================
    # Startup Events
    # ================================
    @app.on_event("startup")
    async def startup_event():
        """Initialize connections and resources"""
        redis_manager.connect()
        print("INFO: Startup complete")
    
    # ================================
    # Shutdown Events
    # ================================
    @app.on_event("shutdown")
    async def shutdown_event():
        """Cleanup connections and resources"""
        redis_manager.disconnect()
        print("INFO: Shutdown complete")
    
    # ================================
    # Register Routers
    # ================================
    app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
    app.include_router(offers_router, prefix="/offers", tags=["Offers"])
    
    return app


# Create application instance
app = create_app()


# ================================
# Root Endpoint
# ================================
@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "message": "StudentVerse API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }
