from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.organizations.schemas import OrganizationInput


class TeamInput(OrganizationInput):
    pass


class TeamOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    name: str
    created_at: datetime


class TeamList(BaseModel):
    items: list[TeamOutput]
    next_cursor: UUID | None = None


class TeamMemberInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    membership_id: UUID
