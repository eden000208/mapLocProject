from fastapi import APIRouter, Depends

from ..dependencies import current_user
from ..services import system as service

router = APIRouter()


@router.get("/health")
def health():
    return service.health()


@router.get("/config")
def public_config(user=Depends(current_user)):
    return service.public_config(user)
