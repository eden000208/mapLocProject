import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from .controllers import auth, detail_upload, query, stations, system
from .services import query as query_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    query_service.start_maintenance()
    yield
    query_service.stop_maintenance()


app = FastAPI(title="BSQ 基站圈选查询", lifespan=lifespan)
for router in (
    auth.router,
    stations.router,
    query.router,
    detail_upload.router,
    system.router,
):
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
    labels = {
        "lng": "经度",
        "lat": "纬度",
        "username": "账号",
        "password": "密码",
        "name": "姓名",
        "station_name": "基站名称",
        "district": "区县",
        "service_center": "营服",
        "page": "页码",
        "size": "每页条数",
        "months": "查询月份",
        "cells": "所选小区",
        "reason": "查询事由",
        "zoom": "地图缩放级别",
        "radius": "圈选半径（米）",
        "center": "圆心坐标",
        "mapping": "导入列映射",
        "coord_sys": "原始坐标系",
        "role": "账号类型",
        "file": "上传文件",
        "type": "选择类型",
        "network": "查询网络",
        "old_password": "原密码",
        "new_password": "新密码",
    }
    messages = []
    for error in exc.errors():
        field = next((labels[x] for x in error["loc"] if x in labels), "请求参数")
        kind, context = error["type"], error.get("ctx", {})
        rule = {
            "missing": "必须填写",
            "int_parsing": "必须为整数",
            "float_parsing": "必须为数字",
            "string_type": "必须为文本",
            "bool_parsing": "必须为是或否",
            "json_invalid": "请求内容必须为有效的 JSON",
            "literal_error": "请选择页面提供的选项",
            "finite_number": "必须为有限数字",
        }.get(kind)
        for code, key, text_rule in (
            ("greater_than_equal", "ge", "必须大于等于"),
            ("less_than_equal", "le", "必须小于等于"),
            ("greater_than", "gt", "必须大于"),
            ("less_than", "lt", "必须小于"),
            ("string_too_short", "min_length", "最少字符数为"),
            ("string_too_long", "max_length", "最多字符数为"),
            ("too_short", "min_length", "最少数量为"),
            ("too_long", "max_length", "最多数量为"),
        ):
            if kind == code:
                rule = f"{text_rule} {context.get(key)}"
        messages.append(field + "：" + (rule or "格式不正确，请按页面提示填写"))
    return error_response(422, "；".join(dict.fromkeys(messages)))


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError):
    return error_response(503, "数据库暂不可用，请检查连接或系统表初始化")


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    return error_response(500, "操作失败，请重试或联系管理员")
