from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

from missions.schemas import MissionFilters

COLUMNS = (
    "missions_uuid, owner_uuid, title, descriptions, location, powers_ids, "
    "work_experience, offer, respondents_uuids, new_respondents_uuids, created_at"
)
EDITABLE_COLUMNS = ("title", "descriptions", "location", "powers_ids", "work_experience", "offer")


class MissionNotFoundError(Exception):
    pass


class AlreadyRespondedError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Mission:
    missions_uuid: UUID
    owner_uuid: UUID
    title: str
    descriptions: str | None
    location: str | None
    powers_ids: list[int]
    work_experience: int
    offer: int | None
    respondents_uuids: list[UUID]
    new_respondents_uuids: list[UUID]
    created_at: datetime


class MissionRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def create(self, owner_uuid: UUID, values: dict[str, Any]) -> Mission:
        columns = [column for column in EDITABLE_COLUMNS if column in values]
        placeholders = ", ".join(f"${i}" for i in range(2, len(columns) + 2))
        row = await self._conn.fetchrow(
            f"INSERT INTO missions (owner_uuid, {', '.join(columns)}) VALUES ($1, {placeholders}) RETURNING {COLUMNS}",
            owner_uuid,
            *(values[column] for column in columns),
        )
        return Mission(**row)

    async def get(self, missions_uuid: UUID) -> Mission | None:
        row = await self._conn.fetchrow(f"SELECT {COLUMNS} FROM missions WHERE missions_uuid = $1", missions_uuid)
        return Mission(**row) if row else None

    async def search(self, filters: MissionFilters) -> list[Mission]:
        conditions: list[str] = []
        args: list[Any] = []

        def add(condition: str, value: Any) -> None:
            args.append(value)
            conditions.append(condition.format(f"${len(args)}"))

        if filters.min_offer is not None:
            add("offer >= {}", filters.min_offer)
        if filters.max_offer is not None:
            add("offer <= {}", filters.max_offer)
        if filters.max_work_experience is not None:
            add("work_experience <= {}", filters.max_work_experience)
        if filters.powers_ids:
            add("powers_ids && {}::int[]", filters.powers_ids)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        args += [filters.limit, filters.offset]
        rows = await self._conn.fetch(
            f"SELECT {COLUMNS} FROM missions {where} ORDER BY created_at DESC, missions_uuid LIMIT ${len(args) - 1} OFFSET ${len(args)}",
            *args,
        )
        return [Mission(**row) for row in rows]

    async def update(self, missions_uuid: UUID, changes: dict[str, Any]) -> Mission | None:
        columns = [column for column in EDITABLE_COLUMNS if column in changes]
        if not columns:
            raise ValueError("Nothing to update")
        assignments = ", ".join(f"{column} = ${i}" for i, column in enumerate(columns, start=2))
        row = await self._conn.fetchrow(
            f"UPDATE missions SET {assignments} WHERE missions_uuid = $1 RETURNING {COLUMNS}",
            missions_uuid,
            *(changes[column] for column in columns),
        )
        return Mission(**row) if row else None

    async def delete(self, missions_uuid: UUID) -> bool:
        return await self._conn.fetchval(
            "DELETE FROM missions WHERE missions_uuid = $1 RETURNING true", missions_uuid
        ) is not None

    async def respond(self, missions_uuid: UUID, hero_uuid: UUID) -> UUID:
        """Returns the mission owner to notify."""
        # The condition is re-checked on the locked row, so concurrent responses can't duplicate a hero.
        owner_uuid = await self._conn.fetchval(
            """
            UPDATE missions
            SET new_respondents_uuids = array_append(new_respondents_uuids, $2)
            WHERE missions_uuid = $1
              AND NOT ($2 = ANY(new_respondents_uuids) OR $2 = ANY(respondents_uuids))
            RETURNING owner_uuid
            """,
            missions_uuid,
            hero_uuid,
        )
        if owner_uuid is not None:
            return owner_uuid
        if await self.get(missions_uuid) is None:
            raise MissionNotFoundError
        raise AlreadyRespondedError

    async def mark_viewed(self, missions_uuid: UUID, respondents_uuids: list[UUID]) -> Mission | None:
        """Moves the given uuids from new_respondents_uuids to respondents_uuids, unknown ones are ignored."""
        row = await self._conn.fetchrow(
            f"""
            UPDATE missions
            SET respondents_uuids = respondents_uuids
                    || ARRAY(SELECT u FROM unnest(new_respondents_uuids) AS u WHERE u = ANY($2::uuid[])),
                new_respondents_uuids =
                    ARRAY(SELECT u FROM unnest(new_respondents_uuids) AS u WHERE u <> ALL($2::uuid[]))
            WHERE missions_uuid = $1
            RETURNING {COLUMNS}
            """,
            missions_uuid,
            respondents_uuids,
        )
        return Mission(**row) if row else None
