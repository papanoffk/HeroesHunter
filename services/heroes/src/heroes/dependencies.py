from collections.abc import AsyncIterator, Callable
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import Depends, Header, HTTPException, Request, status
from pydantic import ValidationError

from heroes.config import Settings, get_settings
from heroes.repository import HeroRepository, PowerRepository
from heroes.schemas import Principal, Role

SettingsDep = Annotated[Settings, Depends(get_settings)]


async def get_connection(request: Request) -> AsyncIterator[asyncpg.Connection]:
    pool: asyncpg.Pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        yield conn


ConnectionDep = Annotated[asyncpg.Connection, Depends(get_connection)]


def get_hero_repository(conn: ConnectionDep) -> HeroRepository:
    return HeroRepository(conn)


def get_power_repository(conn: ConnectionDep) -> PowerRepository:
    return PowerRepository(conn)


HeroRepositoryDep = Annotated[HeroRepository, Depends(get_hero_repository)]
PowerRepositoryDep = Annotated[PowerRepository, Depends(get_power_repository)]


def get_principal(
    client_id: Annotated[str | None, Header(alias="X-Client-Id")] = None,
    role: Annotated[str | None, Header(alias="X-Client-Role")] = None,
) -> Principal:
    """Identity is set by the API gateway after verifying the token in auth."""
    try:
        return Principal.model_validate({"client_id": client_id, "role": role})
    except ValidationError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthenticated") from None


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def require_roles(*roles: Role) -> Callable[[Principal], Principal]:
    """Usage: `Depends(require_roles(Role.CORPORATION))`."""

    def checker(principal: PrincipalDep) -> Principal:
        if principal.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return principal

    return checker


def require_owner(client_uuid: UUID, principal: PrincipalDep) -> Principal:
    if principal.client_id != client_uuid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access to another hero is forbidden")
    return principal


OwnerDep = Annotated[Principal, Depends(require_owner)]
