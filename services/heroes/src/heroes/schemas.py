from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class Role(StrEnum):
    HERO = "hero"
    CORPORATION = "corporation"


class Principal(BaseModel):
    client_id: UUID
    role: Role


class HeroResponse(BaseModel):
    client_uuid: UUID
    name: str
    image_url: str | None


class PowerResponse(BaseModel):
    power_id: int
    title: str
