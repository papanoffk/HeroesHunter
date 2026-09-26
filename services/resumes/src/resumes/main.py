from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from resumes.api import router
from resumes.config import get_settings
from resumes.db import create_pool
from resumes.events import connect_publisher


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.db_pool = await create_pool(settings)
    app.state.publisher = await connect_publisher(settings)
    try:
        yield
    finally:
        await app.state.publisher.close()
        await app.state.db_pool.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Heroes Hunter Resumes", lifespan=lifespan)
    app.include_router(router)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
