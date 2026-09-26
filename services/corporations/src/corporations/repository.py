from dataclasses import dataclass
from uuid import UUID

import asyncpg


class CorpAlreadyExistsError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Corp:
    client_uuid: UUID
    name: str
    description: str | None
    has_image: bool


class CorpRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def create(self, client_uuid: UUID, name: str, description: str | None, image: bytes | None) -> Corp:
        try:
            await self._conn.execute(
                "INSERT INTO corp (client_uuid, name, description, image) VALUES ($1, $2, $3, $4)",
                client_uuid,
                name,
                description,
                image,
            )
        except asyncpg.UniqueViolationError as exc:
            raise CorpAlreadyExistsError from exc
        return Corp(client_uuid, name, description, image is not None)

    async def get(self, client_uuid: UUID) -> Corp | None:
        row = await self._conn.fetchrow(
            "SELECT client_uuid, name, description, image IS NOT NULL AS has_image FROM corp WHERE client_uuid = $1",
            client_uuid,
        )
        return Corp(**row) if row else None

    async def get_image(self, client_uuid: UUID) -> bytes | None:
        return await self._conn.fetchval("SELECT image FROM corp WHERE client_uuid = $1", client_uuid)

    async def update(
        self, client_uuid: UUID, name: str | None, description: str | None, image: bytes | None
    ) -> Corp | None:
        row = await self._conn.fetchrow(
            """
            UPDATE corp
            SET name = COALESCE($2, name), description = COALESCE($3, description), image = COALESCE($4, image)
            WHERE client_uuid = $1
            RETURNING client_uuid, name, description, image IS NOT NULL AS has_image
            """,
            client_uuid,
            name,
            description,
            image,
        )
        return Corp(**row) if row else None
