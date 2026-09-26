from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from heroes.api import heroes_router, powers_router
from heroes.config import get_settings
from heroes.db import create_pool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.db_pool = await create_pool(get_settings())
    try:
        yield
    finally:
        await app.state.db_pool.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Heroes Hunter Heroes", lifespan=lifespan)
    # Must go first: otherwise /v1/heroes/powers is matched as /v1/heroes/{client_uuid}.
    app.include_router(powers_router)
    app.include_router(heroes_router)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
