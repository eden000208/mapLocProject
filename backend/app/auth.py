import hashlib
import secrets
from datetime import timedelta
from typing import Literal

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, false, or_, select
from sqlalchemy.orm import Session

from .audit import log_event
from .config import settings
from .db import get_db
from .models import LoginSession, Station, User, utcnow

router = APIRouter()
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return _hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def user_payload(user: User, csrf_token: str = "") -> dict:
    # 管理员拥有全局管理能力，前端据此显示明文入口；最终数据权限仍由后端复核。
    return {
        key: getattr(user, key)
        for key in (
            "id",
            "username",
            "name",
            "role",
            "is_active",
            "view_plain",
            "districts",
            "service_centers",
            "must_change_pwd",
        )
    } | {
        "view_plain": bool(user.view_plain or user.role == "admin"),
        "csrf_token": csrf_token,
    }


def cell_visible(user: User, station: Station) -> bool:
    if not station.is_active:
        return False
    if user.role == "admin":
        return True
    return station.district in (user.districts or []) or station.service_center in (
        user.service_centers or []
    )


def visible_filter(user: User):
    if user.role == "admin":
        return True
    parts = []
    if user.districts:
        parts.append(Station.district.in_(user.districts))
    if user.service_centers:
        parts.append(Station.service_center.in_(user.service_centers))
    return or_(*parts) if parts else false()


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("bsq_session", "")
    session = db.get(LoginSession, token_hash(token)) if token else None
    if not session:
        raise HTTPException(401, "请先登录")
    user = db.get(User, session.user_id)
    if (
        not user
        or not user.is_active
        or utcnow() - session.last_seen
        > timedelta(minutes=settings.session_idle_minutes)
    ):
        db.delete(session)
        db.commit()
        raise HTTPException(401, "登录已失效")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf = request.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(csrf, session.csrf_token):
            raise HTTPException(403, "请求校验失败，请刷新页面")
    if user.must_change_pwd and request.url.path not in (
        "/api/auth/me",
        "/api/auth/logout",
        "/api/auth/change-password",
    ):
        raise HTTPException(403, "请先修改初始密码")
    session.last_seen = utcnow()
    db.commit()
    request.state.csrf_token = session.csrf_token
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "仅管理员可操作")
    return user


def require_query(user: User = Depends(current_user)) -> User:
    # 管理员也可访问查询、地图及导出菜单。
    if user.role not in ("admin", "analyst"):
        raise HTTPException(403, "当前账号无查询权限")
    return user


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


@router.post("/auth/login")
def login(body: LoginBody, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(
        select(User).where(User.username == body.username).with_for_update()
    )
    if user and user.locked_until and user.locked_until > utcnow():
        raise HTTPException(429, "账号暂时锁定，请稍后重试")
    if (
        not user
        or not user.is_active
        or not verify_password(body.password, user.password_hash)
    ):
        if user:
            user.failed_count += 1
            if user.failed_count >= settings.login_max_fail:
                user.locked_until = utcnow() + timedelta(
                    minutes=settings.login_lock_minutes
                )
                user.failed_count = 0
        log_event(db, user.id if user else None, "login_failed")
        db.commit()
        raise HTTPException(401, "用户名或密码错误")
    user.failed_count = 0
    user.locked_until = None
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(
        LoginSession(
            token_hash=token_hash(token),
            user_id=user.id,
            csrf_token=csrf,
            last_seen=utcnow(),
        )
    )
    log_event(db, user.id, "login")
    db.commit()
    response.set_cookie(
        "bsq_session",
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/api",
    )
    return user_payload(user, csrf)


@router.get("/auth/me")
def me(request: Request, user: User = Depends(current_user)):
    return user_payload(user, request.state.csrf_token)


@router.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    db.execute(
        delete(LoginSession).where(
            LoginSession.token_hash
            == token_hash(request.cookies.get("bsq_session", ""))
        )
    )
    log_event(db, user.id, "logout")
    db.commit()
    response.delete_cookie("bsq_session", path="/api")
    return {"ok": True}


@router.post("/auth/change-password")
def change_password(
    body: PasswordBody,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(400, "旧密码错误")
    if body.old_password == body.new_password:
        raise HTTPException(422, "新密码不能与旧密码相同")
    user.password_hash = hash_password(body.new_password)
    user.must_change_pwd = False
    db.execute(
        delete(LoginSession).where(
            LoginSession.user_id == user.id,
            LoginSession.token_hash
            != token_hash(request.cookies.get("bsq_session", "")),
        )
    )
    log_event(db, user.id, "change_password")
    db.commit()
    return user_payload(user, request.state.csrf_token)


def clean_scopes(data: dict) -> dict:
    for field in ("districts", "service_centers"):
        if field in data and data[field] is not None:
            values = data[field]
            if any(len(v) > 100 for v in values):
                raise HTTPException(422, "区域名称过长")
            data[field] = sorted({v.strip() for v in values if v.strip()})
    return data


@router.get("/admin/users")
def users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [user_payload(u) for u in db.scalars(select(User).order_by(User.id))]


@router.post("/admin/users")
def create_user(
    body: UserBody, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    data = clean_scopes(body.model_dump())
    if db.scalar(select(User.id).where(User.username == body.username)):
        raise HTTPException(409, "用户名已存在")
    password = data.pop("password")
    user = User(**data, password_hash=hash_password(password), must_change_pwd=True)
    db.add(user)
    db.flush()
    log_event(db, admin.id, "create_user", {"target_id": user.id})
    db.commit()
    return user_payload(user)


@router.patch("/admin/users/{user_id}")
def edit_user(
    user_id: int,
    body: UserPatch,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    # 锁定所有有效管理员，避免并发更新使最后一个管理员失效。
    active_admins = list(
        db.scalars(
            select(User)
            .where(User.role == "admin", User.is_active.is_(True))
            .with_for_update()
        )
    )
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "账号不存在")
    data = clean_scopes(body.model_dump(exclude_unset=True, exclude_none=True))
    if user.role == "admin" and user.is_active and len(active_admins) <= 1:
        if data.get("role", user.role) != "admin" or not data.get("is_active", True):
            raise HTTPException(409, "不能停用或降级最后一个管理员")
    if "username" in data and db.scalar(
        select(User.id).where(User.username == data["username"], User.id != user_id)
    ):
        raise HTTPException(409, "用户名已存在")
    password = data.pop("password", None)
    for key, value in data.items():
        setattr(user, key, value)
    if password:
        user.password_hash = hash_password(password)
        user.must_change_pwd = True
        user.failed_count = 0
        user.locked_until = None
    if password or not user.is_active:
        db.execute(delete(LoginSession).where(LoginSession.user_id == user_id))
    log_event(db, admin.id, "edit_user", {"target_id": user_id})
    db.commit()
    return user_payload(user)


@router.get("/meta/scope-options")
def scope_options(user: User = Depends(current_user), db: Session = Depends(get_db)):
    condition = True if user.role == "admin" else visible_filter(user)
    rows = list(
        db.execute(select(Station.district, Station.service_center).where(condition))
    )
    return {
        "districts": sorted({r[0] for r in rows if r[0]}),
        "service_centers": sorted({r[1] for r in rows if r[1]}),
    }
