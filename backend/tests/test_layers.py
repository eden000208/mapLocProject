"""检查 HTTP 边界、依赖身份与业务层委派，不连接数据库。"""

import ast
import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.controllers import auth, detail_upload, query, stations, system
from app.db import get_db
from app.dependencies import current_user, require_admin, require_query
from app.dto.auth import LoginBody
from app.main import app


CONTROLLERS = (auth, stations, query, detail_upload, system)
ENDPOINTS = [
    (controller, route.endpoint)
    for controller in CONTROLLERS
    for route in controller.router.routes
]


@pytest.mark.parametrize(
    "controller,endpoint",
    ENDPOINTS,
    ids=[f"{module.__name__}.{fn.__name__}" for module, fn in ENDPOINTS],
)
def test_each_endpoint_forwards_all_parameters_once(controller, endpoint, monkeypatch):
    arguments = {name: object() for name in inspect.signature(endpoint).parameters}
    result = object()
    delegate = (
        AsyncMock(return_value=result)
        if inspect.iscoroutinefunction(endpoint)
        else MagicMock(return_value=result)
    )
    monkeypatch.setattr(controller.service, endpoint.__name__, delegate)
    if inspect.iscoroutinefunction(endpoint):
        response = asyncio.run(endpoint(**arguments))
        delegate.assert_awaited_once_with(*arguments.values())
    else:
        response = endpoint(**arguments)
        delegate.assert_called_once_with(*arguments.values())
    assert response is result


def test_layers_and_dependency_identity():
    assert auth.current_user is current_user
    assert require_admin.__defaults__[0].dependency is current_user
    assert require_query.__defaults__[0].dependency is current_user
    assert auth.current_user is stations.require_admin.__defaults__[0].dependency
    assert auth.require_admin is detail_upload.require_admin is require_admin
    assert stations.require_query is query.require_query is require_query
    assert system.current_user is current_user
    assert auth.LoginBody is LoginBody
    expected_dependencies = {
        "current_user": current_user,
        "require_admin": require_admin,
        "require_query": require_query,
        "get_db": get_db,
    }

    def check_dependencies(dependant):
        for child in dependant.dependencies:
            assert child.call is expected_dependencies[child.call.__name__]
            check_dependencies(child)

    for controller in CONTROLLERS:
        for route in controller.router.routes:
            check_dependencies(route.dependant)
        tree = ast.parse(Path(controller.__file__).read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert len(node.body) == 1 and isinstance(node.body[0], ast.Return)
        service_tree = ast.parse(
            Path(controller.service.__file__).read_text(encoding="utf-8")
        )
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"APIRouter", "Depends", "File", "Form", "Query"}
            for node in ast.walk(service_tree)
        )


@pytest.mark.parametrize(
    "method,url,payload,controller,function,expected_args",
    [
        (
            "post",
            "/api/auth/login",
            {"username": "mock-admin", "password": "mock-password"},
            auth,
            "login",
            3,
        ),
        (
            "get",
            "/api/admin/stations?page=2&size=7",
            None,
            stations,
            "admin_stations",
            5,
        ),
        ("get", "/api/meta/months?nets=other", None, query, "months", 2),
        (
            "post",
            "/api/admin/detail-import/mock-batch/preview",
            None,
            detail_upload,
            "preview",
            3,
        ),
        ("get", "/api/config", None, system, "public_config", 1),
        ("get", "/api/health", None, system, "health", 0),
    ],
)
def test_http_boundary_delegates_with_resolved_inputs(
    method, url, payload, controller, function, expected_args, monkeypatch
):
    user = SimpleNamespace(id=1, role="admin")
    db = object()
    delegate = MagicMock(return_value={"mock": True})
    monkeypatch.setattr(controller.service, function, delegate)
    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).request(method, url, json=payload)
        assert response.status_code == 200
        assert response.json() == {"mock": True}
        delegate.assert_called_once()
        args = delegate.call_args.args
        assert len(args) == expected_args
        if function == "login":
            assert isinstance(args[0], LoginBody) and args[2] is db
        elif function == "admin_stations":
            assert args == ("", 2, 7, user, db)
        elif function == "months":
            assert args == ("other", user)
        elif function == "preview":
            assert args == ("mock-batch", user, db)
        elif function == "public_config":
            assert args == (user,)
    finally:
        app.dependency_overrides.clear()
