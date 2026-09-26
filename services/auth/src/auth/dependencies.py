from collections.abc import AsyncIterator, Callable
from typing import Annotated

import asyncpg
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError

from auth.config import Settings, get_settings
from auth.repository import ClientRepository
from auth.schemas import Role, TokenPayload
from auth.security import decode_access_token

SettingsDep = Annotated[Settings, Depends(get_settings)]

bearer_scheme = HTTPBearer(auto_error=False)


async def get_connection(request: Request) -> AsyncIterator[asyncpg.Connection]:
    pool: asyncpg.Pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        yield conn


def get_client_repository(
    conn: Annotated[asyncpg.Connection, Depends(get_connection)],
) -> ClientRepository:
    return ClientRepository(conn)


ClientRepositoryDep = Annotated[ClientRepository, Depends(get_client_repository)]


def get_token_payload(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: SettingsDep,
) -> TokenPayload:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        return decode_access_token(credentials.credentials, settings)
    except (jwt.InvalidTokenError, ValidationError):
        raise unauthorized from None


TokenPayloadDep = Annotated[TokenPayload, Depends(get_token_payload)]


def require_roles(*roles: Role) -> Callable[[TokenPayload], TokenPayload]:
    """Usage: `Depends(require_roles(Role.CORPORATION))`."""

    def checker(payload: TokenPayloadDep) -> TokenPayload:
        if payload.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return payload

    return checker
