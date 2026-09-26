import httpx2

from gateway.config import Settings

CLIENT_ID_HEADER = "X-Client-Id"
CLIENT_ROLE_HEADER = "X-Client-Role"
IDENTITY_HEADERS = frozenset({CLIENT_ID_HEADER.lower(), CLIENT_ROLE_HEADER.lower()})


class InvalidTokenError(Exception):
    pass


class AuthUnavailableError(Exception):
    pass


def extract_token(authorization: str | None, query_token: str | None = None) -> str | None:
    """Bearer token from the header, or from the query for browser WebSockets that can't set headers."""
    if authorization is not None:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise InvalidTokenError
        return token.strip()
    return query_token or None


async def verify_token(client: httpx2.AsyncClient, settings: Settings, token: str) -> dict[str, str]:
    """Returns the identity headers for the services."""
    try:
        response = await client.get(
            f"{settings.auth_url}/auth/verify", headers={"Authorization": f"Bearer {token}"}
        )
    except httpx2.RequestError as exc:
        raise AuthUnavailableError from exc
    if response.status_code == 401:
        raise InvalidTokenError
    if response.status_code != 200:
        raise AuthUnavailableError(f"auth /verify returned {response.status_code}")
    return {
        CLIENT_ID_HEADER: response.headers[CLIENT_ID_HEADER],
        CLIENT_ROLE_HEADER: response.headers[CLIENT_ROLE_HEADER],
    }
