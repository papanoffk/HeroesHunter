from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from auth.config import Settings
from auth.schemas import Role, TokenPayload

password_hash = PasswordHash.recommended()

# Verified against when the client is not found, so a failed login takes the
# same time whether or not the email exists (prevents user enumeration).
DUMMY_HASH = password_hash.hash("dummy-password")


def create_access_token(client_id: UUID, role: Role, settings: Settings) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_ttl_minutes)
    payload = {"client_id": str(client_id), "role": role.value, "exp": expire}
    return jwt.encode(
        payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str, settings: Settings) -> TokenPayload:
    """Raises jwt.InvalidTokenError or pydantic.ValidationError on a bad token."""
    payload = jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "client_id", "role"]},
    )
    return TokenPayload.model_validate(payload)
