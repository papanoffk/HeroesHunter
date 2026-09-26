from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, EmailStr, Field

# Must match rows seeded into the `roles` table by migrations.
class Role(StrEnum):
    HERO = "hero"
    CORPORATION = "corporation"


NormalizedEmail = Annotated[EmailStr, AfterValidator(str.lower)]


class RegisterRequest(BaseModel):
    email: NormalizedEmail
    password: str = Field(min_length=8, max_length=128)
    role: Role


class LoginRequest(BaseModel):
    email: NormalizedEmail
    password: str = Field(max_length=128)
    role: Role


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ClientResponse(BaseModel):
    client_id: UUID
    email: str
    role: Role
    created_at: datetime


class TokenPayload(BaseModel):
    client_id: UUID
    role: Role
    exp: datetime
