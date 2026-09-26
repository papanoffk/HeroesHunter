from dataclasses import dataclass
from uuid import UUID

import asyncpg


class HeroAlreadyExistsError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Hero:
    client_uuid: UUID
    name: str
    has_image: bool


@dataclass(frozen=True, slots=True)
class Power:
    power_id: int
    title: str


class HeroRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def create(self, client_uuid: UUID, name: str, image: bytes | None) -> Hero:
        try:
            await self._conn.execute(
                "INSERT INTO hero (client_uuid, name, image) VALUES ($1, $2, $3)",
                client_uuid,
                name,
                image,
            )
        except asyncpg.UniqueViolationError as exc:
            raise HeroAlreadyExistsError from exc
        return Hero(client_uuid, name, image is not None)

    async def get(self, client_uuid: UUID) -> Hero | None:
        row = await self._conn.fetchrow(
            "SELECT client_uuid, name, image IS NOT NULL AS has_image FROM hero WHERE client_uuid = $1",
            client_uuid,
        )
        return Hero(**row) if row else None

    async def get_image(self, client_uuid: UUID) -> bytes | None:
        return await self._conn.fetchval("SELECT image FROM hero WHERE client_uuid = $1", client_uuid)

    async def update(self, client_uuid: UUID, name: str | None, image: bytes | None) -> Hero | None:
        row = await self._conn.fetchrow(
            """
            UPDATE hero
            SET name = COALESCE($2, name), image = COALESCE($3, image)
            WHERE client_uuid = $1
            RETURNING client_uuid, name, image IS NOT NULL AS has_image
            """,
            client_uuid,
            name,
            image,
        )
        return Hero(**row) if row else None


class PowerRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def list(self) -> list[Power]:
        rows = await self._conn.fetch("SELECT power_id, title FROM powers ORDER BY power_id")
        return [Power(**row) for row in rows]

    async def get(self, power_id: int) -> Power | None:
        row = await self._conn.fetchrow("SELECT power_id, title FROM powers WHERE power_id = $1", power_id)
        return Power(**row) if row else None
