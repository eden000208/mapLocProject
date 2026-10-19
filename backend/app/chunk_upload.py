"""Bounded sequential upload parts; final validation uses existing import service."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import storage
from .config import settings
from .db import get_db
from .dependencies import require_admin
from .models import ImportBatch, User, utcnow
from .services import detail_upload

router = APIRouter()
PART_SIZE = 8 * 1024 * 1024


class UploadBody(BaseModel):
    filename: str
    network: str
    size: int = Field(gt=0, le=detail_upload.MAX_BYTES)


def own(db, upload_id, user):
    batch = db.scalar(
        select(ImportBatch)
        .where(ImportBatch.id == str(upload_id), ImportBatch.user_id == user.id)
        .with_for_update()
    )
    if not batch or not batch.filename.startswith("chunks:"):
        raise HTTPException(404, "上传不存在")
    if (utcnow() - batch.created_at).total_seconds() > 86400:
        raise HTTPException(410, "上传已过期")
    return batch


@router.post("/admin/detail-uploads")
def create(
    body: UploadBody, user: User = Depends(require_admin), db: Session = Depends(get_db)
):
    detail_upload.target_table(body.network)
    suffix = Path(body.filename).suffix.lower()
    if suffix not in (".csv", ".xlsx"):
        raise HTTPException(422, "仅支持 CSV 或 XLSX 文件")
    upload_id = str(uuid.uuid4())
    batch = ImportBatch(
        id=upload_id,
        user_id=user.id,
        filename=f"chunks:{body.network}",
        path=str(settings.data_dir / "chunks" / upload_id),
        status="CHUNK_UPLOADING",
        preview={
            "size": body.size,
            "received": 0,
            "parts": 0,
            "network": body.network,
            "suffix": suffix,
        },
    )
    db.add(batch)
    db.commit()
    return {"id": upload_id, "part_size": PART_SIZE}


@router.put("/admin/detail-uploads/{upload_id}/parts/{part}")
async def put_part(
    upload_id: uuid.UUID,
    part: int,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    batch = own(db, upload_id, user)
    state = dict(batch.preview)
    if batch.status != "CHUNK_UPLOADING" or part != state["parts"]:
        raise HTTPException(409, "请按顺序上传文件分片")
    expected = min(PART_SIZE, state["size"] - state["received"])
    if expected <= 0:
        raise HTTPException(409, "文件已上传完成")
    path = Path(batch.path) / f"{part}.part"
    path.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with path.open("wb") as output:
            async for chunk in request.stream():
                size += len(chunk)
                if size > expected:
                    raise HTTPException(413, "分片大小不正确")
                output.write(chunk)
        if size != expected:
            raise HTTPException(422, "分片不完整")
        storage.persist(path)
        state.update(received=state["received"] + size, parts=part + 1)
        batch.preview = state
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return {"received": state["received"]}


@router.post("/admin/detail-uploads/{upload_id}/complete")
def complete(
    upload_id: uuid.UUID,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    batch = own(db, upload_id, user)
    if batch.status == "CHUNK_COMPLETE":
        return batch.preview["result"]
    if batch.status != "CHUNK_UPLOADING":
        raise HTTPException(409, "文件正在合并，请等待当前操作")
    state = dict(batch.preview)
    if state["received"] != state["size"]:
        raise HTTPException(409, "请先上传完整文件")
    batch.status = "CHUNK_ASSEMBLING"
    db.commit()
    path = Path(batch.path) / ("complete" + state["suffix"])
    try:
        with path.open("wb") as output:
            for index in range(state["parts"]):
                source = storage.restore(Path(batch.path) / f"{index}.part")
                with source.open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        output.write(chunk)
        # Existing upload validation and persistent ImportBatch remain authoritative.
        with path.open("rb") as stream:
            result = detail_upload.upload(
                UploadFile(stream, filename="detail" + state["suffix"]),
                state["network"],
                user,
                db,
            )
        batch.status = "CHUNK_COMPLETE"
        batch.preview = state | {"result": result}
        db.commit()
    except Exception:
        db.rollback()
        batch.status = "CHUNK_UPLOADING"
        db.commit()
        raise
    finally:
        path.unlink(missing_ok=True)
    for index in range(state["parts"]):
        storage.remove(Path(batch.path) / f"{index}.part")
    return result
