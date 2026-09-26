import asyncpg

from auth.config import Settings


async def create_pool(settings: Settings) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        dsn=settings.dsn(),
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
    )
