from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db
from ..dependencies import require_admin, require_query
from ..dto.stations import PreviewBody, SelectionBody, StationPatch
from ..models import User
from ..services import stations as service

router = APIRouter()


@router.get("/admin/stations/template")
def template(user: User = Depends(require_admin)):
    return service.template(user)


@router.post("/admin/stations/import")
async def upload(
    file: UploadFile = File(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return await service.upload(file, user, db)


@router.post("/admin/stations/import/{batch_id}/preview")
def preview(
    batch_id: str,
    body: PreviewBody,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service.preview(batch_id, body, user, db)


@router.post("/admin/stations/import/{batch_id}/confirm")
def confirm(
    batch_id: str, user: User = Depends(require_admin), db: Session = Depends(get_db)
):
    return service.confirm(batch_id, user, db)


@router.get("/admin/stations/import/{batch_id}/errors")
def errors_csv(
    batch_id: str, user: User = Depends(require_admin), db: Session = Depends(get_db)
):
    return service.errors_csv(batch_id, user, db)


@router.get("/admin/stations")
def admin_stations(
    q: str = "",
    page: int = 1,
    size: int = 50,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service.admin_stations(q, page, size, user, db)


@router.patch("/admin/stations/{station_id}")
def edit_station(
    station_id: int,
    body: StationPatch,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service.edit_station(station_id, body, user, db)


@router.get("/stations")
def map_stations(
    bbox: str = "-180,-90,180,90",
    zoom: int = 12,
    q: str = "",
    user: User = Depends(require_query),
    db: Session = Depends(get_db),
):
    return service.map_stations(bbox, zoom, q, user, db)


@router.post("/selections/resolve")
def resolve(
    body: SelectionBody,
    user: User = Depends(require_query),
    db: Session = Depends(get_db),
):
    return service.resolve(body, user, db)
