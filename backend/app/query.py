"""轻量持久化查询队列与 XLSX 结果导出。"""

import logging
import math
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from typing import Literal

import xlsxwriter
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.orm import Session

from .audit import log_event
from .auth import require_query
from .config import settings
from .datasource import (
    SourceUnavailable,
    available_months,
    configured_sources,
    stream_batch,
)
from .db import SessionLocal, get_db
from .models import ImportBatch, QueryRow, QueryTask, User, utcnow
from .stations import validate_cells

router = APIRouter()
logger = logging.getLogger(__name__)
TERMINAL = {"SUCCESS", "FAILED", "CANCELLED", "EXPIRED"}
TASK_FIELDS = (
    "id",
    "status",
    "cell_keys",
    "months",
    "nets",
    "purpose",
    "rows_local",
    "rows_other",
    "uniq_local",
    "uniq_other",
    "completed_batches",
    "total_batches",
    "error",
    "created_at",
    "expire_at",
)
RESULT_FIELDS = (
    "month_id",
    "uid",
    "device_number",
    "cell_name",
    "street_name",
    "cell_id",
    "lac",
)
_executor: ThreadPoolExecutor | None = None
_slots: threading.BoundedSemaphore | None = None
_maintenance_thread: threading.Thread | None = None
_stop = threading.Event()
_runtime_lock = threading.Lock()
_recovery_lock = threading.Lock()
_recovered = False


class CellKey(BaseModel):
    lac: int = Field(ge=0, le=9223372036854775807)
    cell_id: int = Field(ge=0, le=9223372036854775807)


class QueryBody(BaseModel):
    cells: list[CellKey] = Field(min_length=1, max_length=100000)
    months: list[str] = Field(min_length=1, max_length=24)
    nets: list[Literal["local", "other"]] = Field(min_length=1, max_length=2)
    purpose: str = Field(min_length=1, max_length=500)

    @field_validator("months")
    @classmethod
    def valid_months(cls, values):
        if any(not value or len(value) > 16 for value in values):
            raise ValueError("Invalid month")
        return list(dict.fromkeys(values))

    @field_validator("purpose")
    @classmethod
    def valid_purpose(cls, value):
        value = value.strip()
        if len(value) < 5:
            raise ValueError("Purpose is too short")
        return value


def task_payload(task: QueryTask) -> dict:
    payload = {key: getattr(task, key) for key in TASK_FIELDS}
    for key in ("created_at", "expire_at"):
        value = payload[key]
        if value is not None:
            payload[key] = value.isoformat(timespec="seconds") + "Z"
    return payload


def mask_number(value: str) -> str:
    value = str(value or "")
    if len(value) <= 7:
        return "*" * len(value)
    return value[:3] + "*" * (len(value) - 7) + value[-4:]


def row_payload(row: QueryRow, plain: bool, include_uid: bool = True) -> dict:
    values = {
        key: getattr(row, key)
        for key in RESULT_FIELDS
        if (plain and (key != "uid" or include_uid)) or key != "uid"
    }
    if not plain:
        values["device_number"] = mask_number(values["device_number"])
    return values


def authorized_task(db: Session, user: User, task_id: str, ready=False):
    task = db.get(QueryTask, task_id)
    if not task or task.user_id != user.id:
        raise HTTPException(404, "查询不存在")
    if task.status == "EXPIRED" or (task.expire_at and task.expire_at <= utcnow()):
        raise HTTPException(410, "查询结果已过期")
    validate_cells(db, user, task.cell_keys)
    if ready and task.status != "SUCCESS":
        raise HTTPException(409, "查询尚未成功完成")
    return task


def check_plain(user: User, plain: bool) -> None:
    if plain and getattr(user, "role", None) != "admin" and not user.view_plain:
        raise HTTPException(403, "没有明文查看权限")


def net_list(value: str) -> list[str]:
    nets = list(dict.fromkeys(value.split(",")))
    if not nets or any(net not in ("local", "other") for net in nets):
        raise HTTPException(422, "网别无效")
    return nets


@router.get("/meta/months")
def months(nets: str = "local,other", user: User = Depends(require_query)):
    try:
        return {"months": available_months(net_list(nets))}
    except SourceUnavailable as exc:
        raise HTTPException(503, "请先配置明细表及字段映射") from exc
    except Exception as exc:
        raise HTTPException(503, "无法读取明细月份，请检查数据库连接和映射") from exc


def ensure_runtime() -> None:
    global _executor, _slots
    with _runtime_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=settings.query_workers, thread_name_prefix="bsq-query"
            )
            _slots = threading.BoundedSemaphore(
                settings.query_workers + settings.query_queue
            )


def ensure_recovered() -> None:
    global _recovered
    with _recovery_lock:
        if not _recovered:
            recover_tasks()
            _recovered = True


@router.post("/queries")
def create_query(
    body: QueryBody,
    user: User = Depends(require_query),
    db: Session = Depends(get_db),
):
    cells = validate_cells(db, user, [cell.model_dump() for cell in body.cells])
    if len(cells) > settings.max_cells or len(body.months) > settings.max_months:
        raise HTTPException(422, "超过小区或月份上限")
    nets = list(dict.fromkeys(body.nets))
    try:
        configured_sources(nets)
        valid_months = available_months(nets)
    except SourceUnavailable as exc:
        raise HTTPException(503, "请先配置明细表及字段映射") from exc
    except Exception as exc:
        raise HTTPException(503, "无法连接明细数据库") from exc
    if any(month not in valid_months for month in body.months):
        raise HTTPException(422, "所选月份不存在")
    ensure_runtime()
    try:
        ensure_recovered()
    except Exception as exc:
        raise HTTPException(503, "系统数据库暂不可用") from exc
    if not _slots.acquire(blocking=False):
        raise HTTPException(429, "查询队列已满，请稍后重试")
    try:
        task = QueryTask(
            id=str(uuid.uuid4()),
            user_id=user.id,
            cell_keys=[{"lac": cell.lac, "cell_id": cell.cell_id} for cell in cells],
            months=body.months,
            nets=nets,
            purpose=body.purpose,
            total_batches=math.ceil(len(cells) / settings.cell_batch)
            * len(body.months)
            * len(nets),
            expire_at=utcnow() + timedelta(hours=settings.result_ttl_hours),
        )
        db.add(task)
        log_event(
            db,
            user.id,
            "query_created",
            {
                "task_id": task.id,
                "cells": len(cells),
                "months": body.months,
                "nets": nets,
            },
        )
        db.commit()
        _executor.submit(run_task, task.id)
        return task_payload(task)
    except Exception:
        _slots.release()
        raise


@router.get("/queries")
def list_queries(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    user: User = Depends(require_query),
    db: Session = Depends(get_db),
):
    condition = QueryTask.user_id == user.id
    tasks = db.scalars(
        select(QueryTask)
        .where(condition)
        .order_by(QueryTask.created_at.desc(), QueryTask.id.desc())
    )
    items = []
    for task in tasks:
        try:
            validate_cells(db, user, task.cell_keys)
        except HTTPException:
            continue
        items.append(task_payload(task))
    return {"items": items[(page - 1) * size : page * size], "total": len(items)}


@router.get("/queries/{task_id}")
def get_query(
    task_id: str, user: User = Depends(require_query), db: Session = Depends(get_db)
):
    return task_payload(authorized_task(db, user, task_id))


@router.post("/queries/{task_id}/cancel")
def cancel_query(
    task_id: str, user: User = Depends(require_query), db: Session = Depends(get_db)
):
    task = authorized_task(db, user, task_id)
    if task.status not in TERMINAL:
        db.execute(
            update(QueryTask)
            .where(
                QueryTask.id == task.id, QueryTask.status.in_(["PENDING", "RUNNING"])
            )
            .values(cancel_requested=True)
        )
        log_event(db, user.id, "query_cancel", {"task_id": task.id})
        db.commit()
        db.refresh(task)
    return task_payload(task)


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
    task = authorized_task(db, user, task_id, ready=True)
    check_plain(user, plain)
    query_rows = db.scalars(
        select(QueryRow)
        .where(QueryRow.task_id == task.id, QueryRow.net == net)
        .order_by(QueryRow.id)
        .offset((page - 1) * size)
        .limit(size)
    )
    items = [row_payload(row, plain, include_uid=net == "local") for row in query_rows]
    if plain:
        log_event(db, user.id, "view_plain", {"task_id": task.id, "net": net})
        db.commit()
    return {"items": items, "total": getattr(task, f"rows_{net}")}


class TaskInterrupted(Exception):
    pass


def check_clock(started: float) -> None:
    if _stop.is_set():
        raise TaskInterrupted("服务正在停止，请重新查询")
    if time.monotonic() - started > settings.query_timeout_seconds:
        raise TaskInterrupted("查询超时，请缩小范围")


def check_running(db: Session, task_id: str, started: float) -> None:
    check_clock(started)
    # 开启新事务，读取接口已提交的取消标记。
    db.expire_all()
    task = db.get(QueryTask, task_id)
    db.rollback()
    if not task or task.cancel_requested:
        raise TaskInterrupted("查询已取消")


def persist_rows(db: Session, values: list[dict]) -> None:
    if values:
        db.execute(insert(QueryRow), values)
        db.commit()


def finish_failed(task_id: str, message: str, cancelled: bool) -> None:
    with SessionLocal() as db:
        task = db.get(QueryTask, task_id)
        if not task:
            return
        db.execute(delete(QueryRow).where(QueryRow.task_id == task_id))
        task.status = "CANCELLED" if cancelled else "FAILED"
        task.error = message
        task.rows_local = task.rows_other = task.uniq_local = task.uniq_other = 0
        task.finished_at = utcnow()
        log_event(
            db,
            task.user_id,
            "query_finished",
            {
                "task_id": task_id,
                "status": task.status,
            },
        )
        db.commit()


def run_task(task_id: str) -> None:
    started = time.monotonic()
    try:
        with SessionLocal() as db:
            task = db.get(QueryTask, task_id)
            if not task:
                return
            user = db.get(User, task.user_id)
            if not user or not user.is_active or user.role not in ("admin", "analyst"):
                raise TaskInterrupted("账号权限已变化")
            validate_cells(db, user, task.cell_keys)
            task.status = "RUNNING"
            db.commit()
            cells, months_, nets = task.cell_keys, task.months, task.nets
            sources = configured_sources(nets)
            counts = {"local": 0, "other": 0}
            completed = 0
            for net in nets:
                for month in months_:
                    for offset in range(0, len(cells), settings.cell_batch):
                        check_running(db, task_id, started)
                        remaining = settings.max_rows - sum(counts.values())
                        stream = stream_batch(
                            sources[net],
                            month,
                            cells[offset : offset + settings.cell_batch],
                            remaining + 1,
                        )
                        buffer = []
                        try:
                            for row_index, row in enumerate(stream):
                                check_clock(started)
                                if row_index % 500 == 0:
                                    check_running(db, task_id, started)
                                counts[net] += 1
                                if sum(counts.values()) > settings.max_rows:
                                    raise TaskInterrupted(
                                        "结果行数超过上限，请缩小范围"
                                    )
                                value = {
                                    key: None if row.get(key) is None else str(row[key])
                                    for key in RESULT_FIELDS
                                    if key not in ("lac", "cell_id")
                                }
                                value["device_number"] = value["device_number"] or ""
                                value.update(
                                    task_id=task_id,
                                    net=net,
                                    lac=int(row["lac"]),
                                    cell_id=int(row["cell_id"]),
                                )
                                buffer.append(value)
                                if len(buffer) >= 500:
                                    persist_rows(db, buffer)
                                    buffer = []
                            persist_rows(db, buffer)
                        finally:
                            stream.close()
                        completed += 1
                        db.execute(
                            update(QueryTask)
                            .where(QueryTask.id == task_id)
                            .values(
                                completed_batches=completed,
                                rows_local=counts["local"],
                                rows_other=counts["other"],
                            )
                        )
                        db.commit()
            check_running(db, task_id, started)
            db.rollback()
            db.expire_all()
            user = db.get(User, task.user_id)
            if not user or not user.is_active or user.role not in ("admin", "analyst"):
                raise TaskInterrupted("账号权限已变化")
            validate_cells(db, user, cells)
            uniq = dict(
                db.execute(
                    select(
                        QueryRow.net, func.count(func.distinct(QueryRow.device_number))
                    )
                    .where(QueryRow.task_id == task_id)
                    .group_by(QueryRow.net)
                ).all()
            )
            # 锁定最终状态，避免并发取消被完成状态覆盖。
            db.rollback()
            task = db.scalar(
                select(QueryTask).where(QueryTask.id == task_id).with_for_update()
            )
            if task.cancel_requested:
                raise TaskInterrupted("查询已取消")
            task.status = "SUCCESS"
            task.uniq_local, task.uniq_other = (
                uniq.get("local", 0),
                uniq.get("other", 0),
            )
            task.finished_at = utcnow()
            task.expire_at = utcnow() + timedelta(hours=settings.result_ttl_hours)
            log_event(
                db,
                task.user_id,
                "query_finished",
                {
                    "task_id": task_id,
                    "status": "SUCCESS",
                    "rows": sum(counts.values()),
                },
            )
            db.commit()
    except TaskInterrupted as exc:
        finish_failed(task_id, str(exc), str(exc) == "查询已取消")
    except Exception:
        # 数据库异常可能包含明细值，日志中禁止记录异常原文。
        try:
            finish_failed(task_id, "查询失败，请检查数据库连接及字段映射", False)
        except Exception:
            logger.warning("Could not persist query failure state")
    finally:
        if _slots is not None:
            _slots.release()


def export_path(task_id: str, plain: bool) -> Path:
    folder = settings.data_dir / "exports"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{task_id}-{uuid.uuid4()}-{'plain' if plain else 'masked'}.xlsx"


def write_xlsx(db: Session, task: QueryTask, path: Path, plain: bool) -> None:
    with xlsxwriter.Workbook(
        str(path),
        {
            "constant_memory": True,
            "strings_to_formulas": False,
            "strings_to_urls": False,
        },
    ) as book:
        header = book.add_format({"bold": True, "bg_color": "#E8ECF0"})
        generated_at = utcnow().isoformat(timespec="seconds") + "Z"
        watermark = f"BSQ 用户 {task.user_id} | {task.id} | {generated_at}"
        for net, title in (("local", "本网明细"), ("other", "异网明细")):
            sheet = book.add_worksheet(title)
            sheet.set_header(f"&C{watermark}")
            keys = [
                key
                for key in RESULT_FIELDS
                if (key != "uid" or (plain and net == "local"))
            ]
            sheet.freeze_panes(1, 0)
            sheet.set_column(0, len(keys) - 1, 22)
            sheet.write_row(0, 0, keys, header)
            result = db.scalars(
                select(QueryRow)
                .where(QueryRow.task_id == task.id, QueryRow.net == net)
                .order_by(QueryRow.id)
                .execution_options(yield_per=500)
            )
            for index, row in enumerate(result, 1):
                payload = row_payload(row, plain, include_uid=net == "local")
                sheet.write_row(index, 0, [payload[key] for key in keys])
            sheet.autofilter(0, 0, getattr(task, f"rows_{net}"), len(keys) - 1)
        sheet = book.add_worksheet("摘要")
        sheet.set_header(f"&C{watermark}")
        sheet.set_column(0, 0, 24)
        sheet.set_column(1, 1, 60)
        summary = [
            ("查询编号", task.id),
            ("查询事由", task.purpose),
            ("导出用户编号", task.user_id),
            ("导出时间 UTC", generated_at),
            ("月份", ", ".join(task.months)),
            ("小区数量", len(task.cell_keys)),
            ("本网行数", task.rows_local),
            ("异网行数", task.rows_other),
            ("本网去重号码", task.uniq_local),
            ("异网去重号码", task.uniq_other),
            ("明文", "是" if plain else "否"),
        ]
        for index, values in enumerate(summary):
            sheet.write_row(index, 0, values)


@router.post("/queries/{task_id}/export")
def export(
    task_id: str,
    plain: bool = False,
    user: User = Depends(require_query),
    db: Session = Depends(get_db),
):
    task = authorized_task(db, user, task_id, ready=True)
    check_plain(user, plain)
    path = export_path(task.id, plain)
    try:
        write_xlsx(db, task, path, plain)
        # 长时间导出完成后，再次检查权限和结果有效期。
        db.rollback()
        db.expire_all()
        user = db.get(User, user.id)
        if not user or not user.is_active or user.role not in ("admin", "analyst"):
            raise HTTPException(403, "账号权限已变化")
        check_plain(user, plain)
        authorized_task(db, user, task.id, ready=True)
        log_event(db, user.id, "export", {"task_id": task.id, "plain": plain})
        db.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return FileResponse(
        path,
        filename=f"BSQ-{task.id}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def recover_tasks() -> None:
    with SessionLocal() as db:
        ids = list(
            db.scalars(
                select(QueryTask.id).where(QueryTask.status.in_(["PENDING", "RUNNING"]))
            )
        )
        if ids:
            db.execute(delete(QueryRow).where(QueryRow.task_id.in_(ids)))
            db.execute(
                update(QueryTask)
                .where(QueryTask.id.in_(ids))
                .values(
                    status="FAILED",
                    error="服务重启，请重新查询",
                    finished_at=utcnow(),
                    rows_local=0,
                    rows_other=0,
                    uniq_local=0,
                    uniq_other=0,
                )
            )
            db.commit()


def cleanup_expired() -> None:
    with SessionLocal() as db:
        ids = list(
            db.scalars(
                select(QueryTask.id).where(
                    QueryTask.expire_at <= utcnow(),
                    QueryTask.status.in_(TERMINAL - {"EXPIRED"}),
                )
            )
        )
        if ids:
            db.execute(delete(QueryRow).where(QueryRow.task_id.in_(ids)))
            db.execute(
                update(QueryTask)
                .where(QueryTask.id.in_(ids))
                .values(
                    status="EXPIRED",
                    rows_local=0,
                    rows_other=0,
                    uniq_local=0,
                    uniq_other=0,
                )
            )
            db.commit()
        batches = list(
            db.scalars(
                select(ImportBatch)
                .where(
                    ImportBatch.created_at
                    <= utcnow() - timedelta(hours=settings.result_ttl_hours)
                )
                .with_for_update()
            )
        )
        imports = (settings.data_dir / "imports").resolve()
        for batch in batches:
            path = Path(batch.path).resolve()
            if path.parent == imports and path.suffix.lower() in (".csv", ".xlsx"):
                path.unlink(missing_ok=True)
            db.delete(batch)
        if batches:
            db.commit()
    folder = settings.data_dir / "exports"
    threshold = time.time() - settings.result_ttl_hours * 3600
    if folder.exists():
        for path in folder.glob("*.xlsx"):
            if any(path.name.startswith(f"{task_id}-") for task_id in ids) or (
                path.stat().st_mtime < threshold
            ):
                path.unlink(missing_ok=True)


def maintenance_loop() -> None:
    while not _stop.is_set():
        try:
            ensure_recovered()
            cleanup_expired()
        except Exception:
            logger.warning("Query maintenance unavailable; will retry")
        _stop.wait(60)


def start_maintenance() -> None:
    global _maintenance_thread, _recovered
    _recovered = False
    ensure_runtime()
    _stop.clear()
    _maintenance_thread = threading.Thread(
        target=maintenance_loop, daemon=True, name="bsq-maintenance"
    )
    _maintenance_thread.start()


def stop_maintenance() -> None:
    global _executor, _slots, _maintenance_thread
    _stop.set()
    if _maintenance_thread:
        _maintenance_thread.join(timeout=6)
    if _executor:
        _executor.shutdown(wait=True, cancel_futures=False)
    _executor = _slots = _maintenance_thread = None
