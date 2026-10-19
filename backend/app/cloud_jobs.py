"""Polling jobs for long Cloudflare HTTP operations; payloads stay in MySQL/R2."""

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import storage
from .config import settings
from .db import SessionLocal
from .dependencies import current_user
from .models import User, utcnow
from .services import detail_upload, query

router = APIRouter()
executor: ThreadPoolExecutor | None = None
executor_lock = threading.Lock()
slots = threading.BoundedSemaphore(4)
BOOT_ID = str(uuid.uuid4())


def pool():
    global executor
    with executor_lock:
        if executor is None:
            executor = ThreadPoolExecutor(
                max_workers=2, thread_name_prefix="bsq-operation"
            )
        return executor


def stop():
    global executor
    if executor:
        executor.shutdown(wait=True)
        executor = None


class JobBody(BaseModel):
    kind: str
    target: uuid.UUID
    plain: bool = False


def job_path(job_id: str) -> Path:
    return settings.data_dir / "operations" / f"{uuid.UUID(job_id)}.json"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    temporary.replace(path)
    storage.persist(path)


def authorized(record, user):
    if record["user_id"] != user.id:
        raise HTTPException(404, "操作不存在")
    if record["expires"] <= utcnow().isoformat():
        raise HTTPException(410, "操作已过期")


def perform(path, record):
    try:
        with SessionLocal() as db:
            user = db.get(User, record["user_id"])
            if not user or not user.is_active or user.must_change_pwd:
                raise HTTPException(403, "账号权限已变化")
            target = record["target"]
            if record["kind"] == "export":
                response = query.export(target, record["plain"], user, db)
                output = Path(response.path)
                storage.persist(output)
                record["file"] = str(output)
            else:
                if user.role != "admin":
                    raise HTTPException(403, "仅管理员可操作")
                if record["kind"] == "assemble":
                    from .chunk_upload import complete

                    action = complete
                else:
                    action = (
                        detail_upload.preview
                        if record["kind"] == "preview"
                        else detail_upload.confirm
                    )
                record["result"] = action(target, user, db)
            record["status"] = "SUCCESS"
    except HTTPException as exc:
        record.update(status="FAILED", message=str(exc.detail))
    except Exception:
        record.update(status="FAILED", message="操作失败，请检查连接后重试")
    finally:
        try:
            save(path, record)
        finally:
            slots.release()


@router.post("/operations")
def create(body: JobBody, user: User = Depends(current_user)):
    if body.kind not in ("export", "preview", "confirm", "assemble"):
        raise HTTPException(422, "操作类型无效")
    with SessionLocal() as db:
        if body.kind == "export":
            query.authorized_task(db, user, str(body.target), ready=True)
            query.check_plain(user, body.plain)
        else:
            if user.role != "admin":
                raise HTTPException(403, "仅管理员可操作")
            if body.kind == "assemble":
                from .chunk_upload import own

                own(db, body.target, user)
            else:
                detail_upload.own_batch(db, str(body.target), user)
    if not slots.acquire(blocking=False):
        raise HTTPException(429, "操作队列已满，请稍后重试")
    job_id = str(uuid.uuid4())
    record = dict(
        id=job_id,
        user_id=user.id,
        kind=body.kind,
        target=str(body.target),
        plain=body.plain,
        status="RUNNING",
        boot=BOOT_ID,
        expires=(utcnow() + timedelta(minutes=30)).isoformat(),
    )
    try:
        save(job_path(job_id), record)
        pool().submit(perform, job_path(job_id), record)
    except Exception:
        slots.release()
        raise
    return {"id": job_id}


def read(job_id, user):
    path = job_path(str(job_id))
    try:
        record = json.loads(storage.restore(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(404, "操作不存在") from None
    authorized(record, user)
    if record["status"] == "RUNNING" and record.get("boot") != BOOT_ID:
        record.update(status="FAILED", message="服务已重启，请核对导入状态后重试")
        save(path, record)
    return record


@router.get("/operations/{job_id}")
def status(job_id: uuid.UUID, user: User = Depends(current_user)):
    record = read(job_id, user)
    # Revalidate current scope even after a job completed.
    with SessionLocal() as db:
        if record["kind"] == "export":
            query.authorized_task(db, user, record["target"], ready=True)
            query.check_plain(user, record["plain"])
        elif user.role != "admin":
            raise HTTPException(403, "仅管理员可操作")
    return {
        key: record[key]
        for key in ("id", "status", "message", "result")
        if key in record
    }


@router.get("/operations/{job_id}/file")
def download(job_id: uuid.UUID, user: User = Depends(current_user)):
    record = read(job_id, user)
    if record["kind"] != "export" or record["status"] != "SUCCESS":
        raise HTTPException(409, "文件尚未就绪")
    path = storage.restore(record["file"])
    with SessionLocal() as db:
        fresh_user = db.get(User, user.id)
        if (
            not fresh_user
            or not fresh_user.is_active
            or fresh_user.must_change_pwd
            or fresh_user.role not in ("admin", "analyst")
        ):
            raise HTTPException(403, "账号权限已变化")
        query.authorized_task(db, fresh_user, record["target"], ready=True)
        query.check_plain(fresh_user, record["plain"])
    return FileResponse(path, filename="BSQ.xlsx")
