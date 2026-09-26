from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from notifications.api import router
from notifications.config import get_settings
from notifications.connections import ConnectionManager
from notifications.consumer import start_consumer


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.connection_manager = ConnectionManager()
    app.state.consumer = await start_consumer(get_settings(), app.state.connection_manager)
    try:
        yield
    finally:
        await app.state.consumer.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="Heroes Hunter Notifications", lifespan=lifespan)
    app.include_router(router)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
