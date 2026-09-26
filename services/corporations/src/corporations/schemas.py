from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class Role(StrEnum):
    HERO = "hero"
    CORPORATION = "corporation"


class Principal(BaseModel):
    client_id: UUID
    role: Role


class CorpResponse(BaseModel):
    client_uuid: UUID
    name: str
    description: str | None
    image_url: str | None
