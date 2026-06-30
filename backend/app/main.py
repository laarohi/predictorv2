"""FastAPI application entry point."""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config import get_settings
from app.database import init_db
from app.services.score_scheduler import scheduler_lifespan


def configure_logging(level: str) -> None:
    """Route app (`app.*`) logs to stdout so they surface in `docker logs`.

    Without this the app's loggers propagate to the root logger, which under
    uvicorn has NO handler configured — so Python's last-resort handler silently
    drops everything below WARNING, and we lose all INFO-level operational logs
    (score sync, the scheduler, push sends). That blind spot is exactly what
    made the knockout-shootout bug impossible to debug from logs.

    Attaches a single stdout handler at the configured level. Idempotent (safe
    on repeated imports / --reload). uvicorn's own loggers carry propagate=False
    and configure no "root", so access/error logs neither duplicate here nor get
    clobbered.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    if any(getattr(h, "_predictor_stdout", False) for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler._predictor_stdout = True  # type: ignore[attr-defined]
    root.addHandler(handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler.

    init_db() runs Alembic migrations on every startup, so the DB always
    converges to the migration head before requests start serving. No
    manual `alembic upgrade head` step required in dev or prod.
    """
    await init_db()
    async with scheduler_lifespan():
        yield


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        description="Football prediction competition API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.debug else None,
        redoc_url="/api/redoc" if settings.debug else None,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routes
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "version": "0.1.0"}

    return app


app = create_app()
