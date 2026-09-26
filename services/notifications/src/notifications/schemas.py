from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Role(StrEnum):
    HERO = "hero"
    CORPORATION = "corporation"


class Principal(BaseModel):
    client_id: UUID
    role: Role


class Event(BaseModel):
    """Only the routing fields are validated, the rest of the payload is forwarded to the client as is."""

    model_config = ConfigDict(extra="allow")

    event: str
    recipient_uuid: UUID
