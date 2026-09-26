from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx2
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gateway.api import router
from gateway.config import Settings, get_settings
from gateway.routing import build_routes


def create_http_client(settings: Settings) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(timeout=settings.upstream_timeout_seconds, follow_redirects=False)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.routes = build_routes(settings)
    app.state.http_client = create_http_client(settings)
    try:
        yield
    finally:
        await app.state.http_client.aclose()


def create_app() -> FastAPI:
    app = FastAPI(title="Heroes Hunter Gateway", lifespan=lifespan)
    settings = get_settings()
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Declared before the catch-all proxy route so it isn't forwarded.
    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router)
    return app


app = create_app()
