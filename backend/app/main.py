import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from . import auth, query, stations
from .config import settings
from .db import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    query.start_maintenance()
    yield
    query.stop_maintenance()


app = FastAPI(title="BSQ 基站圈选查询", lifespan=lifespan)
for router in (auth.router, stations.router, query.router):
    app.include_router(router, prefix="/api")


def error_response(status: int, message: str, code: str | None = None):
    return JSONResponse(
        status_code=status,
        content={
            "code": code or str(status),
            "message": message,
            "trace_id": uuid.uuid4().hex,
        },
    )


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return error_response(exc.status_code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # 校验错误不回显输入值，避免泄露凭据或业务标识。
    return error_response(422, "参数格式错误，请检查必填项与数值范围")


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError):
    return error_response(503, "数据库暂不可用，请检查连接或系统表初始化")


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    return error_response(500, "操作失败，请重试或联系管理员")


@app.get("/api/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "unavailable"})


@app.get("/api/config")
def public_config(user=Depends(auth.current_user)):
    return {
        "tianditu_key": settings.tianditu_key,
        "map_center": [settings.map_center_lng, settings.map_center_lat],
        "map_zoom": settings.map_zoom,
        "min_draw_zoom": settings.min_draw_zoom,
        "max_cells": settings.max_cells,
        "max_months": settings.max_months,
    }
