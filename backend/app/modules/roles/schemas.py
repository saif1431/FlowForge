from typing import Literal

from pydantic import BaseModel, ConfigDict


class RoleOutput(BaseModel):
    code: str
    name: str
    permissions: list[str]


class RoleList(BaseModel):
    items: list[RoleOutput]


class AccessOutput(BaseModel):
    role_code: str
    permissions: list[str]


class RoleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role_code: Literal["admin", "designer", "approver", "member", "viewer"]
