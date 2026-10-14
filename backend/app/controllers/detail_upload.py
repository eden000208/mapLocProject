from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db
from ..dependencies import require_admin
from ..models import User
from ..services import detail_upload as service

router = APIRouter()


@router.post("/admin/detail-import")
def upload(
    file: UploadFile = File(...),
    network: str = Form(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service.upload(file, network, user, db)


@router.post("/admin/detail-import/{batch_id}/preview")
def preview(
    batch_id: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service.preview(batch_id, user, db)


@router.post("/admin/detail-import/{batch_id}/confirm")
def confirm(
    batch_id: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service.confirm(batch_id, user, db)
