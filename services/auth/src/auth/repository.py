from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import asyncpg

from auth.schemas import Role


class ClientAlreadyExistsError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Client:
    client_uuid: UUID
    email: str
    pass_hash: str
    role: Role
    created_at: datetime


class ClientRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def create(self, email: str, pass_hash: str, role: Role) -> Client:
        try:
            row = await self._conn.fetchrow(
                """
                INSERT INTO client (email, pass_hash, role_id)
                SELECT $1, $2, role_id FROM roles WHERE role_name = $3
                RETURNING client_uuid, created_at
                """,
                email,
                pass_hash,
                role.value,
            )
        except asyncpg.UniqueViolationError as exc:
            raise ClientAlreadyExistsError from exc
        if row is None:
            raise LookupError(f"Role {role.value!r} is missing in the roles table")
        return Client(row["client_uuid"], email, pass_hash, role, row["created_at"])

    async def get_by_email(self, email: str, role: Role) -> Client | None:
        row = await self._conn.fetchrow(
            """
            SELECT c.client_uuid, c.email, c.pass_hash, r.role_name, c.created_at
            FROM client c
            JOIN roles r USING (role_id)
            WHERE c.email = $1 AND r.role_name = $2
            """,
            email,
            role.value,
        )
        return self._to_client(row)

    async def get_by_id(self, client_uuid: UUID) -> Client | None:
        row = await self._conn.fetchrow(
            """
            SELECT c.client_uuid, c.email, c.pass_hash, r.role_name, c.created_at
            FROM client c
            JOIN roles r USING (role_id)
            WHERE c.client_uuid = $1
            """,
            client_uuid,
        )
        return self._to_client(row)

    @staticmethod
    def _to_client(row: asyncpg.Record | None) -> Client | None:
        if row is None:
            return None
        return Client(
            row["client_uuid"], row["email"], row["pass_hash"], Role(row["role_name"]), row["created_at"]
        )
