from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, JsonValue, SecretStr, field_validator


class EmailInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    email: Annotated[EmailStr, Field(max_length=320)]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class LoginInput(EmailInput):
    password: Annotated[SecretStr, Field(min_length=1, max_length=128)]


class RegisterInput(EmailInput):
    password: Annotated[SecretStr, Field(min_length=15, max_length=128)]


class TokenInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    token: Annotated[SecretStr, Field(min_length=43, max_length=43)]


class ResetInput(TokenInput):
    password: Annotated[SecretStr, Field(min_length=15, max_length=128)]


class UserOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    email_verified_at: datetime | None
    created_at: datetime


class SessionOutput(BaseModel):
    id: UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    current: bool


class SessionList(BaseModel):
    items: list[SessionOutput]


class Message(BaseModel):
    message: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, JsonValue]
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorDetail
