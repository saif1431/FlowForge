from datetime import datetime
from ipaddress import ip_address
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    JsonValue,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    StringConstraints,
    field_validator,
    model_validator,
)

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class EmptyConfig(Input):
    pass


class Assignee(Input):
    kind: Literal["member", "team"]
    id: UUID


class ApprovalConfig(Input):
    assignee: Assignee | None = None
    due_after_minutes: Annotated[int, Field(strict=True, ge=1, le=525600)] | None = None
    decision: Literal["any"] = "any"


class ConditionConfig(Input):
    field: (
        Annotated[
            str, StringConstraints(pattern=r"^input(?:\.[A-Za-z_][A-Za-z0-9_]*)+$", max_length=200)
        ]
        | None
    ) = None
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte"] = "eq"
    value: StrictBool | StrictInt | StrictFloat | StrictStr | None = None

    @field_validator("value", mode="before")
    @classmethod
    def scalar(cls, value: object) -> object:
        import math

        if value is not None and type(value) not in (str, bool, int, float):
            raise ValueError("Expected a JSON scalar")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Expected a finite number")
        if isinstance(value, str) and len(value) > 1000:
            raise ValueError("Comparison value is too long")
        return value


class EmailConfig(Input):
    to: list[Annotated[EmailStr, Field(max_length=320)]] = Field(
        default_factory=list, max_length=10
    )
    subject: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=4000)


class WebhookConfig(Input):
    url: str | None = Field(default=None, max_length=2048)
    method: Literal["POST"] = "POST"

    @field_validator("url")
    @classmethod
    def public_https(cls, value: str | None) -> str | None:
        if value is None:
            return value
        parts = urlsplit(value)
        host = (parts.hostname or "").lower().rstrip(".")
        if (
            parts.scheme != "https"
            or not host
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
            or parts.port not in (None, 443)
            or any(char.isspace() or ord(char) < 32 for char in value)
            or "\\" in value
            or "." not in host
            or host.endswith((".localhost", ".local", ".internal", ".test", ".invalid"))
        ):
            raise ValueError("Expected a public HTTPS URL without credentials or query parameters")
        try:
            address = ip_address(host)
        except ValueError:
            # DNS resolution and rebinding checks belong to the eventual outbound executor.
            if not all(
                part and all(c.isascii() and (c.isalnum() or c == "-") for c in part)
                for part in host.split(".")
            ):
                raise ValueError("Invalid hostname") from None
        else:
            if not address.is_global:
                raise ValueError("Private destinations are not allowed")
        return value


class DelayConfig(Input):
    seconds: Annotated[int, Field(strict=True, ge=1, le=2592000)] | None = None


CONFIG_MODELS: dict[str, type[BaseModel]] = {
    "manual_trigger": EmptyConfig,
    "end": EmptyConfig,
    "approval": ApprovalConfig,
    "condition": ConditionConfig,
    "email": EmailConfig,
    "webhook": WebhookConfig,
    "delay": DelayConfig,
}


class Position(Input):
    x: float = Field(default=0, ge=-100000, le=100000, allow_inf_nan=False)
    y: float = Field(default=0, ge=-100000, le=100000, allow_inf_nan=False)


class NodeInput(Input):
    id: UUID
    kind: Literal["manual_trigger", "approval", "condition", "email", "webhook", "delay", "end"]
    label: str = Field(default="", max_length=120)
    config: dict[str, JsonValue] = Field(default_factory=dict)
    position: Position = Field(default_factory=Position)

    @model_validator(mode="after")
    def config_shape(self) -> NodeInput:
        CONFIG_MODELS[self.kind].model_validate(self.config)
        return self


class EdgeInput(Input):
    id: UUID
    source: UUID
    target: UUID
    branch: Literal["next", "true", "false", "approved", "rejected"] = "next"


class GraphInput(Input):
    nodes: list[NodeInput] = Field(default_factory=list, max_length=64)
    edges: list[EdgeInput] = Field(default_factory=list, max_length=128)


class GraphIssue(BaseModel):
    code: str
    message: str
    node_id: UUID | None = None
    edge_id: UUID | None = None


class GraphValidation(BaseModel):
    valid: bool
    issues: list[GraphIssue]


class WorkflowInput(Input):
    name: Name
    description: str = Field(default="", max_length=1000)


class WorkflowOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    name: str
    description: str
    created_at: datetime


class WorkflowList(BaseModel):
    items: list[WorkflowOutput]
    next_cursor: UUID | None = None


class VersionOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    workflow_id: UUID
    version_number: int
    status: Literal["draft", "published"]
    revision: int
    created_at: datetime
    published_at: datetime | None


class VersionDetail(VersionOutput):
    graph: GraphInput


class WorkflowCreated(BaseModel):
    workflow: WorkflowOutput
    draft: VersionDetail


class VersionList(BaseModel):
    items: list[VersionOutput]
    next_cursor: int | None = None


class VersionPage(Input):
    cursor: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=100)


class RevisionInput(Input):
    expected_revision: int = Field(strict=True, ge=1)


class SaveGraphInput(RevisionInput):
    graph: GraphInput


class DraftInput(Input):
    source_version_id: UUID | None = None
