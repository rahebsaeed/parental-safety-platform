from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from backend.app.core.config import settings
from backend.app.core.security_middleware import SecurityMiddleware
from backend.app.services.realtime import watcher
from backend.app.api.routers import (
    health_router,
    devices_router,
    activity_router,
    domains_router,
    domain_security_router,
    classification_router,
    alerts_router,
    analytics_router,
    realtime_router,
    auth_router,
    router_dns_router,
    openrouter_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Start SQLite change watcher on startup and stop cleanly on shutdown."""
    watcher.start()
    try:
        yield
    finally:
        watcher.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description=(
            "REST API for Parental Safety Platform. "
            "Exposes joined network device discovery (Phase 1) and DNS observation (Phase 2) data."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Enable CORS for local and web development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Apply defense-in-depth security middleware (Rate limiting, Security headers, CSRF)
    app.add_middleware(SecurityMiddleware)

    # Root health endpoint and API prefix endpoints
    app.include_router(health_router)
    app.include_router(health_router, prefix=settings.API_V1_STR)
    app.include_router(devices_router, prefix=settings.API_V1_STR)
    app.include_router(activity_router, prefix=settings.API_V1_STR)
    app.include_router(domains_router, prefix=settings.API_V1_STR)
    app.include_router(domain_security_router, prefix=settings.API_V1_STR)
    app.include_router(classification_router, prefix=settings.API_V1_STR)
    app.include_router(alerts_router, prefix=settings.API_V1_STR)
    app.include_router(analytics_router, prefix=settings.API_V1_STR)
    app.include_router(realtime_router, prefix=settings.API_V1_STR)
    app.include_router(auth_router, prefix=settings.API_V1_STR)
    app.include_router(router_dns_router, prefix=settings.API_V1_STR)
    app.include_router(openrouter_router, prefix=settings.API_V1_STR)

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        """Redirect root to OpenAPI docs."""
        return RedirectResponse(url="/docs")

    return app


app = create_app()
