from typing import Literal

from pydantic import BaseModel, Field


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class PasswordBody(BaseModel):
    old_password: str = Field(max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class UserBody(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[\w.@-]+$")
    name: str = Field(default="", max_length=100)
    password: str = Field(min_length=8, max_length=256)
    role: Literal["admin", "analyst"] = "analyst"
    is_active: bool = True
    view_plain: bool = False
    districts: list[str] = Field(default_factory=list, max_length=500)
    service_centers: list[str] = Field(default_factory=list, max_length=500)


class UserPatch(BaseModel):
    username: str | None = Field(
        default=None, min_length=1, max_length=64, pattern=r"^[\w.@-]+$"
    )
    name: str | None = Field(default=None, max_length=100)
    password: str | None = Field(default=None, min_length=8, max_length=256)
    role: Literal["admin", "analyst"] | None = None
    is_active: bool | None = None
    view_plain: bool | None = None
    districts: list[str] | None = Field(default=None, max_length=500)
    service_centers: list[str] | None = Field(default=None, max_length=500)
