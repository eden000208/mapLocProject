from typing import Literal

from pydantic import BaseModel, Field


class PreviewBody(BaseModel):
    mapping: dict[str, str]
    coord_sys: Literal["WGS84", "GCJ02", "BD09"] = "WGS84"


class StationPatch(BaseModel):
    station_name: str | None = Field(default=None, max_length=200)
    district: str | None = Field(default=None, max_length=100)
    service_center: str | None = Field(default=None, max_length=100)
    lng: float | None = Field(default=None, ge=-180, le=180)
    lat: float | None = Field(default=None, ge=-90, le=90)
    is_active: bool | None = None


class SelectionBody(BaseModel):
    type: Literal["rect", "polygon", "circle", "cells"]
    geometry: dict | None = None
    center: tuple[float, float] | None = None
    radius: float | None = Field(default=None, gt=0, le=100000)
    cells: list[dict] | None = Field(default=None, max_length=100000)
