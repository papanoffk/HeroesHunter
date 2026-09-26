from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from corporations.api import router
from corporations.config import get_settings
from corporations.db import create_pool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.db_pool = await create_pool(get_settings())
    try:
        yield
    finally:
        await app.state.db_pool.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Heroes Hunter Corporations", lifespan=lifespan)
    app.include_router(router)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
