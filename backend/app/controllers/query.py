from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..dependencies import require_query
from ..dto.query import QueryBody
from ..models import User
from ..services import query as service

router = APIRouter()


@router.get("/meta/months")
def months(nets: str = "local,other", user: User = Depends(require_query)):
    return service.months(nets, user)


@router.post("/queries")
def create_query(
    body: QueryBody,
    user: User = Depends(require_query),
    db: Session = Depends(get_db),
):
    return service.create_query(body, user, db)


@router.get("/queries")
def list_queries(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    user: User = Depends(require_query),
    db: Session = Depends(get_db),
):
    return service.list_queries(page, size, user, db)


@router.get("/queries/{task_id}")
def get_query(
    task_id: str, user: User = Depends(require_query), db: Session = Depends(get_db)
):
    return service.get_query(task_id, user, db)


@router.post("/queries/{task_id}/cancel")
def cancel_query(
    task_id: str, user: User = Depends(require_query), db: Session = Depends(get_db)
):
    return service.cancel_query(task_id, user, db)


@router.get("/queries/{task_id}/rows")
def rows(
    task_id: str,
    net: Literal["local", "other"] = "local",
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    plain: bool = False,
    user: User = Depends(require_query),
    db: Session = Depends(get_db),
):
    return service.rows(task_id, net, page, size, plain, user, db)


@router.post("/queries/{task_id}/export")
def export(
    task_id: str,
    plain: bool = False,
    user: User = Depends(require_query),
    db: Session = Depends(get_db),
):
    return service.export(task_id, plain, user, db)
