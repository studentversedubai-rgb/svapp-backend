"""
StudentVerse Backend - FastAPI Application Entry Point

This is the main application file that initializes FastAPI,
registers all routers, and configures middleware.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.redis import redis_manager
from app.modules.auth.router import router as auth_router
from app.modules.admin.router import router as admin_router
from app.modules.offers.router import router as offers_router
from app.modules.orbit.router import router as orbit_router
from app.modules.entitlements.router import router as entitlements_router
from app.modules.merchant.router import router as merchant_router
from app.modules.tickets.router import router as tickets_router
from app.modules.payments.router import router as payments_router
from app.modules.online_deals.router import router as online_deals_router
from app.modules.app_status.router import router as app_status_router
from app.core.config import Settings
from app.core.middleware import SecurityHeadersMiddleware, RequestSizeLimitMiddleware, LoggingMiddleware


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
    # Native iOS/Android clients bypass CORS, so no wildcard is needed.
    # We only allow the merchant dashboard (a browser app) and local dev.
    # All other web origins are blocked by the browser automatically.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://svmerchant.vercel.app",
            "http://studentverseofficial.com",   # production merchant dashboard
            "http://localhost:5173",            # local Vite dev server
            "http://localhost:4173",            # local Vite preview server
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    settings_obj = Settings() # Validate environments immediately on boot
    
    # ================================
    # Security Middlewares
    # ================================
    app.add_middleware(SecurityHeadersMiddleware)

    app.add_middleware(RequestSizeLimitMiddleware, max_upload_size=settings_obj.MAX_UPLOAD_SIZE_BYTES)
    app.add_middleware(LoggingMiddleware)

    # ================================
    # Exception Handlers
    # ================================
    from fastapi.responses import JSONResponse
    from fastapi.exceptions import RequestValidationError
    from fastapi import Request, HTTPException

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        import logging
        log = logging.getLogger(__name__)
        log.error(f"Unhandled Exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "An unexpected error occurred. Please try again later."},
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        detail = exc.detail
        if exc.status_code == 404:
            detail = "Resource not found."
            
        return JSONResponse(
            status_code=exc.status_code,
            content={"ok": False, "error": detail},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        simplified_errors = [f"{'.'.join(str(loc) for loc in error.get('loc', []))}: {error.get('msg')}" for error in errors]
        return JSONResponse(
            status_code=422,
            content={"ok": False, "error": "Validation failed", "details": simplified_errors},
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
    app.include_router(admin_router, prefix="/admin", tags=["Internal Admin"])
    app.include_router(offers_router, prefix="/offers", tags=["Offers"])
    app.include_router(orbit_router, prefix="/orbit", tags=["Orbit AI"])
    app.include_router(entitlements_router, prefix="/entitlements", tags=["Entitlements"])
    app.include_router(merchant_router, prefix="/merchant", tags=["Merchant Validation"])
    app.include_router(tickets_router, prefix="/tickets", tags=["Tickets"])
    app.include_router(payments_router, prefix="/payments", tags=["Payments"])
    app.include_router(online_deals_router, prefix="/api/v1/online-deals", tags=["online-deals"])
    app.include_router(app_status_router, prefix="/app-status", tags=["App Status"])
    
    from app.modules.payments.router import webhook_router
    app.include_router(webhook_router, prefix="/stripe", tags=["Stripe Webhook"])
    
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


# ================================
# Health Check Endpoint
# ================================
@app.get("/health")
async def health():
    """Health check endpoint for Railway"""
    return {"status": "ok", "version": "1.0.0"}
