import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import DomainError, RateLimitedError
from app.core.logging import configure_logging
from app.db.session import dispose_engine, get_sessionmaker

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(debug=settings.debug)
    logger.info("starting api", extra={"environment": settings.environment})
    yield
    await dispose_engine()
    logger.info("api stopped")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Airport Operations API",
        version="1.0.0",
        summary="Flights, ticketing, gates, baggage and immigration for an international airport.",
        lifespan=lifespan,
        # Interactive docs are useful in development and an information leak in production.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    _register_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    _register_health_routes(app)
    _register_root_route(app, settings)

    return app


def _register_root_route(app: FastAPI, settings) -> None:
    @app.get("/", include_in_schema=False)
    async def root() -> Response:
        """Answer the URL a human actually types.

        Without this, `/` is a 404: every route lives under /api/v1, /docs or
        the probes. Anyone opening the deployment URL — which is the first thing
        anyone does — met `{"detail":"Not Found"}` and reasonably concluded the
        service was broken.

        Where docs are served, send them there. In production they are disabled,
        so redirecting would swap one 404 for another; answer with an index that
        at least says what this is and what is reachable.
        """
        if settings.is_production:
            return JSONResponse(
                {
                    "service": app.title,
                    "version": app.version,
                    "docs": "disabled in production",
                    "endpoints": {"api": "/api/v1", "health": "/health", "ready": "/ready"},
                }
            )
        return RedirectResponse(url="/docs")


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        # A 429 without Retry-After tells the client to back off but not for how
        # long, so every client invents its own answer. RFC 9110 defines the
        # header for exactly this; send it.
        headers = (
            {"Retry-After": str(exc.retry_after_seconds)}
            if isinstance(exc, RateLimitedError)
            else None
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "details": exc.details},
            headers=headers,
        )

    @app.exception_handler(IntegrityError)
    async def _integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
        # A constraint we did not translate into a friendly message still must not
        # surface as a 500 with the raw SQL attached.
        logger.warning("unhandled integrity error", exc_info=exc)
        return JSONResponse(
            status_code=409,
            content={
                "code": "constraint_violation",
                "message": "The request conflicts with a database constraint.",
                "details": {},
            },
        )


def _register_health_routes(app: FastAPI) -> None:
    @app.get("/health", tags=["health"], summary="Liveness probe")
    async def health() -> dict[str, str]:
        """Process is up. Deliberately does not touch the database."""
        return {"status": "ok"}

    @app.get("/ready", tags=["health"], summary="Readiness probe")
    async def ready() -> JSONResponse:
        """Dependencies are reachable, so this instance can serve traffic."""
        try:
            async with get_sessionmaker()() as session:
                await session.execute(text("SELECT 1"))
        except Exception as exc:
            logger.error("readiness check failed", exc_info=exc)
            return JSONResponse(
                status_code=503, content={"status": "unavailable", "database": "unreachable"}
            )
        return JSONResponse(status_code=200, content={"status": "ready", "database": "ok"})


app = create_app()
