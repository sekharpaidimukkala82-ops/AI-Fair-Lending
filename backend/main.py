"""
Fair Lending Intelligence Platform – FastAPI application entry point.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import Config
from backend.core.monitoring import get_monitoring_engine

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("fair_lending")


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- Startup ----
    logger.info("Starting Fair Lending Intelligence Platform …")

    # Ensure required directories exist
    Config.ensure_dirs()
    logger.info(f"Upload dir:  {Config.UPLOAD_DIR}")
    logger.info(f"Chroma dir:  {Config.CHROMA_PERSIST_DIR}")
    logger.info(f"Models dir:  {Config.MODELS_DIR}")

    # Warn about missing API key
    warnings = Config.validate()
    for w in warnings:
        logger.warning(w)

    # Init database tables
    from backend.database.connection import init_db, AsyncSessionLocal
    from backend.database.crud import get_user_by_email, create_user
    from backend.auth.security import hash_password

    await init_db()
    logger.info("Database tables initialized.")

    # Create default admin if none exists
    async with AsyncSessionLocal() as db:
        admin = await get_user_by_email(db, "admin@fairlend.ai")
        if not admin:
            await create_user(
                db,
                email="admin@fairlend.ai",
                username="admin",
                hashed_password=hash_password("FairLend@Admin2024"),
                full_name="System Administrator",
                role="admin",
                institution="Fair Lending Platform",
            )
            await db.commit()
            logger.info("Default admin created: admin@fairlend.ai / FairLend@Admin2024")

    logger.info("Platform ready.")

    yield  # application is running here

    # ---- Shutdown ----
    logger.info("Shutting down Fair Lending Intelligence Platform …")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Fair Lending Intelligence Platform",
    description=(
        "AI-powered platform for HMDA fair lending analysis, "
        "disparate impact detection, semantic search, and compliance reporting."
    ),
    version="1.0.0",
    contact={
        "name": "Fair Lending Team",
        "email": "fairlending@example.com",
    },
    license_info={
        "name": "Proprietary",
    },
    lifespan=lifespan,
)

# Priority 4: structured logging + Sentry + Prometheus
from backend.core.p4_startup import init_priority4
init_priority4(app)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*",  # Dev — restrict in production by setting ALLOWED_ORIGINS env var
        # e.g. "https://your-app.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    """Add X-Process-Time header and log slow requests."""
    t0 = time.time()
    response = await call_next(request)
    elapsed = time.time() - t0
    response.headers["X-Process-Time"] = f"{elapsed:.4f}"
    if elapsed > 5.0:
        logger.warning(f"Slow request: {request.method} {request.url.path} – {elapsed:.2f}s")
    return response


# ---------------------------------------------------------------------------
# Exception Handlers
# ---------------------------------------------------------------------------

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={"error": "Not Found", "detail": str(exc.detail), "path": str(request.url.path)},
    )


@app.exception_handler(422)
async def validation_error_handler(request: Request, exc):
    return JSONResponse(
        status_code=422,
        content={"error": "Validation Error", "detail": str(exc)},
    )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    logger.exception(f"Unhandled server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error", "detail": "An unexpected error occurred."},
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

from backend.api.routes import upload, search, chat, fairness, reports, ml, ai_config, auth
from backend.api.routes import ws as ws_router
from backend.api.routes import upload_v2
from backend.api.routes import advanced_fairness, cases, compliance

app.include_router(upload.router,       prefix="/api/v1")
app.include_router(upload_v2.router,    prefix="/api/v1")   # v2: Celery + DB + WebSocket
app.include_router(search.router,       prefix="/api/v1")
app.include_router(chat.router,         prefix="/api/v1")
app.include_router(fairness.router,     prefix="/api/v1")
app.include_router(reports.router,      prefix="/api/v1")
app.include_router(ml.router,           prefix="/api/v1")
app.include_router(ai_config.router,    prefix="/api/v1")
app.include_router(auth.router,         prefix="/api/v1")
app.include_router(ws_router.router)    # WebSocket: /ws/{resource_id}
app.include_router(advanced_fairness.router, prefix="/api/v1")
app.include_router(cases.router,             prefix="/api/v1")
app.include_router(compliance.router,        prefix="/api/v1")

# ---------------------------------------------------------------------------
# Core Endpoints
# ---------------------------------------------------------------------------

@app.get("/", tags=["Root"])
async def root():
    """Root endpoint – confirms the API is running."""
    return {
        "platform": "Fair Lending Intelligence Platform",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "api_prefix": "/api/v1",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "platform": "Fair Lending Intelligence Platform",
        "version": "1.0.0",
    }


@app.get("/monitoring/dashboard", tags=["Monitoring"])
async def monitoring_dashboard():
    """Return aggregated monitoring metrics for the platform dashboard."""
    monitor = get_monitoring_engine()
    return monitor.get_dashboard_data()


@app.get("/monitoring/alerts", tags=["Monitoring"])
async def get_alerts():
    """Return all unresolved monitoring alerts."""
    monitor = get_monitoring_engine()
    alerts = monitor.check_alerts()
    return {"alerts": [a.model_dump() for a in alerts], "count": len(alerts)}


@app.post("/monitoring/alerts/{alert_id}/resolve", tags=["Monitoring"])
async def resolve_alert(alert_id: str):
    """Mark a monitoring alert as resolved."""
    monitor = get_monitoring_engine()
    resolved = monitor.resolve_alert(alert_id)
    if not resolved:
        return JSONResponse(status_code=404, content={"detail": f"Alert '{alert_id}' not found."})
    return {"status": "resolved", "alert_id": alert_id}
