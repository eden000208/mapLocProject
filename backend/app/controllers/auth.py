from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..dependencies import current_user, require_admin
from ..dto.auth import LoginBody, PasswordBody, UserBody, UserPatch
from ..models import User
from ..services import auth as service

router = APIRouter()


@router.post("/auth/login")
def login(body: LoginBody, response: Response, db: Session = Depends(get_db)):
    return service.login(body, response, db)


@router.get("/auth/me")
def me(request: Request, user: User = Depends(current_user)):
    return service.me(request, user)


@router.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.logout(request, response, user, db)


@router.post("/auth/change-password")
def change_password(
    body: PasswordBody,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.change_password(body, request, user, db)


@router.get("/admin/users")
def users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.users(admin, db)


@router.post("/admin/users")
def create_user(
    body: UserBody, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    return service.create_user(body, admin, db)


@router.patch("/admin/users/{user_id}")
def edit_user(
    user_id: int,
    body: UserPatch,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    # 锁定所有有效管理员，避免并发更新使最后一个管理员失效。
    return service.edit_user(user_id, body, admin, db)


@router.get("/meta/scope-options")
def scope_options(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return service.scope_options(user, db)
