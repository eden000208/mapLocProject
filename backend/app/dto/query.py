from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CellKey(BaseModel):
    lac: int = Field(ge=0, le=9223372036854775807)
    cell_id: int = Field(ge=0, le=9223372036854775807)


class QueryBody(BaseModel):
    cells: list[CellKey] = Field(min_length=1, max_length=100000)
    months: list[str] = Field(min_length=1, max_length=24)
    nets: list[Literal["local", "other"]] = Field(min_length=1, max_length=2)
    purpose: str = Field(min_length=1, max_length=500)

    @field_validator("months")
    @classmethod
    def valid_months(cls, values):
        if any(not value or len(value) > 16 for value in values):
            raise ValueError("Invalid month")
        return list(dict.fromkeys(values))

    @field_validator("purpose")
    @classmethod
    def valid_purpose(cls, value):
        value = value.strip()
        if len(value) < 5:
            raise ValueError("Purpose is too short")
        return value
