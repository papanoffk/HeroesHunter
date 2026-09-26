from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

from resumes.schemas import ResumeFilters

COLUMNS = (
    "resume_uuid, owner_uuid, title, descriptions, previous_works, powers_ids, "
    "work_experience, offer, invitations_corp_uuids, new_invitations_corp_uuids, created_at"
)
EDITABLE_COLUMNS = ("title", "descriptions", "previous_works", "powers_ids", "work_experience", "offer")


class ResumeNotFoundError(Exception):
    pass


class AlreadyInvitedError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Resume:
    resume_uuid: UUID
    owner_uuid: UUID
    title: str
    descriptions: str | None
    previous_works: str | None
    powers_ids: list[int]
    work_experience: int
    offer: int | None
    invitations_corp_uuids: list[UUID]
    new_invitations_corp_uuids: list[UUID]
    created_at: datetime


class ResumeRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def create(self, owner_uuid: UUID, values: dict[str, Any]) -> Resume:
        columns = [column for column in EDITABLE_COLUMNS if column in values]
        placeholders = ", ".join(f"${i}" for i in range(2, len(columns) + 2))
        row = await self._conn.fetchrow(
            f"INSERT INTO resume (owner_uuid, {', '.join(columns)}) VALUES ($1, {placeholders}) RETURNING {COLUMNS}",
            owner_uuid,
            *(values[column] for column in columns),
        )
        return Resume(**row)

    async def get(self, resume_uuid: UUID) -> Resume | None:
        row = await self._conn.fetchrow(f"SELECT {COLUMNS} FROM resume WHERE resume_uuid = $1", resume_uuid)
        return Resume(**row) if row else None

    async def search(self, filters: ResumeFilters) -> list[Resume]:
        conditions: list[str] = []
        args: list[Any] = []

        def add(condition: str, value: Any) -> None:
            args.append(value)
            conditions.append(condition.format(f"${len(args)}"))

        if filters.min_offer is not None:
            add("offer >= {}", filters.min_offer)
        if filters.max_offer is not None:
            add("offer <= {}", filters.max_offer)
        if filters.min_work_experience is not None:
            add("work_experience >= {}", filters.min_work_experience)
        if filters.powers_ids:
            add("powers_ids && {}::int[]", filters.powers_ids)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        args += [filters.limit, filters.offset]
        rows = await self._conn.fetch(
            f"SELECT {COLUMNS} FROM resume {where} "
            f"ORDER BY created_at DESC, resume_uuid LIMIT ${len(args) - 1} OFFSET ${len(args)}",
            *args,
        )
        return [Resume(**row) for row in rows]

    async def update(self, resume_uuid: UUID, changes: dict[str, Any]) -> Resume | None:
        columns = [column for column in EDITABLE_COLUMNS if column in changes]
        if not columns:
            raise ValueError("Nothing to update")
        assignments = ", ".join(f"{column} = ${i}" for i, column in enumerate(columns, start=2))
        row = await self._conn.fetchrow(
            f"UPDATE resume SET {assignments} WHERE resume_uuid = $1 RETURNING {COLUMNS}",
            resume_uuid,
            *(changes[column] for column in columns),
        )
        return Resume(**row) if row else None

    async def delete(self, resume_uuid: UUID) -> bool:
        return await self._conn.fetchval(
            "DELETE FROM resume WHERE resume_uuid = $1 RETURNING true", resume_uuid
        ) is not None

    async def invite(self, resume_uuid: UUID, corp_uuid: UUID) -> UUID:
        """Returns the resume owner to notify."""
        # The condition is re-checked on the locked row, so concurrent invitations can't duplicate a corporation.
        owner_uuid = await self._conn.fetchval(
            """
            UPDATE resume
            SET new_invitations_corp_uuids = array_append(new_invitations_corp_uuids, $2)
            WHERE resume_uuid = $1
              AND NOT ($2 = ANY(new_invitations_corp_uuids) OR $2 = ANY(invitations_corp_uuids))
            RETURNING owner_uuid
            """,
            resume_uuid,
            corp_uuid,
        )
        if owner_uuid is not None:
            return owner_uuid
        if await self.get(resume_uuid) is None:
            raise ResumeNotFoundError
        raise AlreadyInvitedError

    async def mark_viewed(self, resume_uuid: UUID, corp_uuids: list[UUID]) -> Resume | None:
        """Moves the given uuids from new_invitations_corp_uuids to invitations_corp_uuids, unknown ones are ignored."""
        row = await self._conn.fetchrow(
            f"""
            UPDATE resume
            SET invitations_corp_uuids = invitations_corp_uuids
                    || ARRAY(SELECT u FROM unnest(new_invitations_corp_uuids) AS u WHERE u = ANY($2::uuid[])),
                new_invitations_corp_uuids =
                    ARRAY(SELECT u FROM unnest(new_invitations_corp_uuids) AS u WHERE u <> ALL($2::uuid[]))
            WHERE resume_uuid = $1
            RETURNING {COLUMNS}
            """,
            resume_uuid,
            corp_uuids,
        )
        return Resume(**row) if row else None
