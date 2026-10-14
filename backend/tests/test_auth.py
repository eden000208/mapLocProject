from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.dependencies import current_user, require_query
from app.dto.auth import UserPatch
from app.models import LoginSession, User, utcnow
from app.services.auth import (
    cell_visible,
    edit_user,
    hash_password,
    user_payload,
    verify_password,
    visible_filter,
)


def test_password():
    encoded = hash_password("example-long-password")
    assert verify_password("example-long-password", encoded)
    assert not verify_password("bad", encoded)
    assert not verify_password("bad", "invalid-hash")


def test_scope_or_and_default_deny():
    station = SimpleNamespace(is_active=True, district="D", service_center="S")
    user = SimpleNamespace(role="analyst", districts=[], service_centers=[])
    assert not cell_visible(user, station)
    user.service_centers = ["S"]
    assert cell_visible(user, station)
    station.is_active = False
    assert not cell_visible(user, station)


def test_admin_scope_all_and_disabled_station_rejected():
    user = User(role="admin", districts=[], service_centers=[], view_plain=False)
    station = SimpleNamespace(is_active=True, district="OTHER", service_center="")
    assert cell_visible(user, station)
    assert visible_filter(user) is True
    assert require_query(user) is user
    assert user_payload(user)["view_plain"] is True
    station.is_active = False
    assert not cell_visible(user, station)


def test_unknown_role_cannot_query():
    with pytest.raises(HTTPException) as exc:
        require_query(User(role="unknown"))
    assert exc.value.status_code == 403


def request(method="GET", path="/api/auth/me", csrf=""):
    headers = [(b"cookie", b"bsq_session=opaque")]
    if csrf:
        headers.append((b"x-csrf-token", csrf.encode()))
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": headers,
            "scheme": "http",
            "server": ("test", 80),
        }
    )


def session_db(expired=False):
    db = MagicMock()
    user = User(id=1, is_active=True, must_change_pwd=False)
    session = LoginSession(
        user_id=1,
        csrf_token="valid",
        last_seen=utcnow() - timedelta(hours=1) if expired else utcnow(),
    )
    db.get.side_effect = [session, user]
    return db, user


def test_idle_invalidates_session():
    db, _ = session_db(True)
    with pytest.raises(HTTPException) as exc:
        current_user(request(), db)
    assert exc.value.status_code == 401
    db.delete.assert_called_once()


def test_csrf_required():
    db, _ = session_db()
    with pytest.raises(HTTPException) as exc:
        current_user(request("POST"), db)
    assert exc.value.status_code == 403


def test_first_password_change_gate():
    db, user = session_db()
    user.must_change_pwd = True
    with pytest.raises(HTTPException) as exc:
        current_user(request(path="/api/stations"), db)
    assert exc.value.status_code == 403


def test_last_admin_cannot_be_disabled():
    admin = User(id=1, role="admin", is_active=True)
    db = MagicMock()
    db.scalars.return_value = [admin]
    db.get.return_value = admin
    with pytest.raises(HTTPException) as exc:
        edit_user(1, UserPatch(is_active=False), admin, db)
    assert exc.value.status_code == 409
    db.commit.assert_not_called()
