from collections.abc import AsyncIterator, Callable
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import Depends, Header, HTTPException, Request, status
from pydantic import ValidationError

from resumes.events import EventPublisher
from resumes.repository import Resume, ResumeRepository
from resumes.schemas import Principal, Role

ClientIdHeader = Annotated[str | None, Header(alias="X-Client-Id")]
ClientRoleHeader = Annotated[str | None, Header(alias="X-Client-Role")]


async def get_connection(request: Request) -> AsyncIterator[asyncpg.Connection]:
    pool: asyncpg.Pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        yield conn


def get_resume_repository(conn: Annotated[asyncpg.Connection, Depends(get_connection)]) -> ResumeRepository:
    return ResumeRepository(conn)


ResumeRepositoryDep = Annotated[ResumeRepository, Depends(get_resume_repository)]


def get_publisher(request: Request) -> EventPublisher:
    return request.app.state.publisher


PublisherDep = Annotated[EventPublisher, Depends(get_publisher)]


def get_principal(client_id: ClientIdHeader = None, role: ClientRoleHeader = None) -> Principal:
    """Identity is set by the API gateway after verifying the token in auth."""
    try:
        return Principal.model_validate({"client_id": client_id, "role": role})
    except ValidationError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthenticated") from None


def get_optional_principal(client_id: ClientIdHeader = None, role: ClientRoleHeader = None) -> Principal | None:
    """For public endpoints: anonymous without headers, but invalid headers are still rejected."""
    if client_id is None and role is None:
        return None
    return get_principal(client_id, role)


PrincipalDep = Annotated[Principal, Depends(get_principal)]
OptionalPrincipalDep = Annotated[Principal | None, Depends(get_optional_principal)]


def require_roles(*roles: Role) -> Callable[[Principal], Principal]:
    """Usage: `Depends(require_roles(Role.CORPORATION))`."""

    def checker(principal: PrincipalDep) -> Principal:
        if principal.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return principal

    return checker


async def get_owned_resume(resume_uuid: UUID, principal: PrincipalDep, repo: ResumeRepositoryDep) -> Resume:
    resume = await repo.get(resume_uuid)
    if resume is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    if resume.owner_uuid != principal.client_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the resume owner can do this")
    return resume


OwnedResumeDep = Annotated[Resume, Depends(get_owned_resume)]
