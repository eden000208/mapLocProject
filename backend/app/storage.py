"""Private R2 persistence through a Container-only outbound binding gateway."""

import http.client
import os
import shutil
import uuid
from pathlib import Path
from urllib.parse import quote, urlsplit

from fastapi import HTTPException

from .config import settings


def object_key(path: Path) -> str:
    return path.resolve().relative_to(settings.data_dir.resolve()).as_posix()


def request(method: str, path: Path, body=None, size: int = 0):
    endpoint = urlsplit(settings.storage_gateway)
    connection = http.client.HTTPConnection(
        endpoint.hostname, endpoint.port, timeout=120
    )
    try:
        headers = {"Content-Length": str(size)} if body is not None else {}
        connection.request(
            method, "/" + quote(object_key(path), safe="/"), body, headers
        )
        response = connection.getresponse()
        if response.status == 404:
            raise HTTPException(410, "文件已过期，请重新上传或生成")
        if response.status >= 300:
            raise HTTPException(503, "文件存储暂不可用")
        if method == "GET":
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
            try:
                with temporary.open("wb") as target:
                    shutil.copyfileobj(response, target, length=1024 * 1024)
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        else:
            response.read()
    except (OSError, http.client.HTTPException):
        raise HTTPException(503, "文件存储暂不可用") from None
    finally:
        connection.close()


def persist(path: Path) -> None:
    if settings.storage_gateway:
        with path.open("rb") as source:
            request("PUT", path, source, path.stat().st_size)


def restore(path: str | Path) -> Path:
    path = Path(path)
    if settings.storage_gateway and not path.exists():
        request("GET", path)
    return path


def remove(path: str | Path) -> None:
    path = Path(path)
    if settings.storage_gateway:
        try:
            request("DELETE", path)
        except HTTPException as exc:
            if exc.status_code != 410:
                raise
    path.unlink(missing_ok=True)
