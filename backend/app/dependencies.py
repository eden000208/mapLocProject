"""共享身份认证及权限依赖；所有路由复用同一函数对象。"""

import secrets
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import LoginSession, User, utcnow
from .services.auth import token_hash


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
