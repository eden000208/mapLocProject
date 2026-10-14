from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ..config import settings
from ..db import engine


def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "unavailable"})


def public_config(user):
    return {
        "tianditu_key": settings.tianditu_key,
        "map_center": [settings.map_center_lng, settings.map_center_lat],
        "map_zoom": settings.map_zoom,
        "min_draw_zoom": settings.min_draw_zoom,
        "max_cells": settings.max_cells,
        "max_months": settings.max_months,
    }
