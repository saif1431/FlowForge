from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class OrganizationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class OrganizationOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    owner_user_id: UUID
    created_at: datetime


class OrganizationList(BaseModel):
    items: list[OrganizationOutput]
    next_cursor: UUID | None = None


class MemberOutput(BaseModel):
    id: UUID
    user_id: UUID
    email: str
    created_at: datetime
    role_code: str


class MemberList(BaseModel):
    items: list[MemberOutput]
    next_cursor: UUID | None = None


class InvitationOutput(BaseModel):
    id: UUID
    organization_id: UUID
    organization_name: str
    email: str
    status: Literal["pending", "accepted", "declined", "revoked", "expired"]
    created_at: datetime
    expires_at: datetime


class InvitationList(BaseModel):
    items: list[InvitationOutput]
    next_cursor: UUID | None = None


class PageInput(BaseModel):
    cursor: UUID | None = None
    limit: int = Field(default=50, ge=1, le=100)
