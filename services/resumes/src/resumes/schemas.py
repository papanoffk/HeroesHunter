from datetime import datetime
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator


class Role(StrEnum):
    HERO = "hero"
    CORPORATION = "corporation"


class Principal(BaseModel):
    client_id: UUID
    role: Role


Title = Annotated[str, Field(min_length=1, max_length=200)]
NonNegativeInt = Annotated[int, Field(ge=0)]


class CreateResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title
    descriptions: str | None = None
    previous_works: str | None = None
    powers_ids: list[PositiveInt] = []
    work_experience: NonNegativeInt = 0
    offer: NonNegativeInt | None = None


class UpdateResumeRequest(BaseModel):
    """Omitted fields are left unchanged, explicit null clears descriptions/previous_works/offer."""

    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    descriptions: str | None = None
    previous_works: str | None = None
    powers_ids: list[PositiveInt] | None = None
    work_experience: NonNegativeInt | None = None
    offer: NonNegativeInt | None = None

    @model_validator(mode="after")
    def check_fields(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        for field in ("title", "powers_ids", "work_experience"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ResumeFilters(BaseModel):
    min_offer: NonNegativeInt | None = None
    max_offer: NonNegativeInt | None = None
    min_work_experience: NonNegativeInt | None = None
    powers_ids: list[PositiveInt] = Field(default=[], description="Resumes having any of these powers")
    limit: int = Field(default=50, ge=1, le=100)
    offset: NonNegativeInt = 0


class ViewRequest(BaseModel):
    invitations_corp_uuids: list[UUID] = Field(min_length=1)


class ResumeResponse(BaseModel):
    resume_uuid: UUID
    owner_uuid: UUID
    title: str
    descriptions: str | None
    previous_works: str | None
    powers_ids: list[int]
    work_experience: int
    offer: int | None
    created_at: datetime
    invitations_corp_uuids: list[UUID] | None = Field(default=None, description="Visible only to the owner")
    new_invitations_corp_uuids: list[UUID] | None = Field(default=None, description="Visible only to the owner")
