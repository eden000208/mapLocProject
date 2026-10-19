"""Cloudflare boundaries: persistence, ownership, bounded upload and jobs."""

import uuid
import queue
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app import cloud_jobs, chunk_upload, storage
from app.mysql_bridge import start_bridge
from app.config import settings
from app.models import utcnow


def test_storage_rejects_paths_outside_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    with pytest.raises(ValueError):
        storage.object_key(tmp_path / "secret.env")


def test_local_storage_remains_usable(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_gateway", "")
    path = tmp_path / "sample.csv"
    path.write_bytes(b"MOCK_ONLY")
    storage.persist(path)
    assert storage.restore(path).read_bytes() == b"MOCK_ONLY"
    storage.remove(path)
    assert not path.exists()


def test_operation_owner_and_expiry():
    record = {"user_id": 1, "expires": "2999-01-01"}
    with pytest.raises(HTTPException) as error:
        cloud_jobs.authorized(record, SimpleNamespace(id=2))
    assert error.value.status_code == 404
    record["expires"] = "2000-01-01"
    with pytest.raises(HTTPException) as error:
        cloud_jobs.authorized(record, SimpleNamespace(id=1))
    assert error.value.status_code == 410


def test_chunk_foreign_owner_rejected_before_file_access():
    db = MagicMock()
    db.scalar.return_value = None
    with pytest.raises(HTTPException) as error:
        chunk_upload.own(db, uuid.uuid4(), SimpleNamespace(id=2))
    assert error.value.status_code == 404


def test_incomplete_chunk_upload_cannot_import():
    db = MagicMock()
    db.scalar.return_value = SimpleNamespace(
        filename="chunks:other",
        created_at=utcnow(),
        status="CHUNK_UPLOADING",
        preview={"size": 100, "received": 50},
    )
    with pytest.raises(HTTPException) as error:
        chunk_upload.complete(uuid.uuid4(), SimpleNamespace(id=1), db)
    assert error.value.status_code == 409
    db.commit.assert_not_called()


def test_completed_chunk_upload_returns_same_result():
    db = MagicMock()
    db.scalar.return_value = SimpleNamespace(
        filename="chunks:other",
        created_at=utcnow(),
        status="CHUNK_COMPLETE",
        preview={"result": {"batch_id": "MOCK_ONLY"}},
    )
    assert chunk_upload.complete(uuid.uuid4(), SimpleNamespace(id=1), db) == {
        "batch_id": "MOCK_ONLY"
    }
    db.commit.assert_not_called()


def test_operation_rechecks_admin_before_work(tmp_path, monkeypatch):
    db = MagicMock()
    db.get.return_value = SimpleNamespace(
        id=1, role="analyst", is_active=True, must_change_pwd=False
    )
    session = MagicMock()
    session.__enter__.return_value = db
    monkeypatch.setattr(cloud_jobs, "SessionLocal", lambda: session)
    saved, action, slots = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(cloud_jobs, "save", saved)
    monkeypatch.setattr(cloud_jobs, "slots", slots)
    monkeypatch.setattr(cloud_jobs.detail_upload, "confirm", action)
    cloud_jobs.perform(
        tmp_path / "operation.json", {"user_id": 1, "kind": "confirm", "target": "mock"}
    )
    action.assert_not_called()
    assert saved.call_args.args[1]["status"] == "FAILED"
    slots.release.assert_called_once()


def test_tcp_bridge_keeps_binary_packets_and_server_greeting(monkeypatch):
    class MockWebSocket:
        def __init__(self):
            self.messages = queue.Queue()
            self.messages.put(b"MOCK_GREETING")

        def recv(self):
            return self.messages.get(timeout=5)

        def send_binary(self, data):
            self.messages.put(data)

        def close(self):
            self.messages.put(b"")

    upstream = MockWebSocket()
    monkeypatch.setitem(
        sys.modules,
        "websocket",
        SimpleNamespace(
            create_connection=lambda *args, **kwargs: upstream,
            WebSocketException=RuntimeError,
        ),
    )
    monkeypatch.setattr(settings, "mysql_bridge_url", "ws://mock.invalid/")
    monkeypatch.setattr(settings, "mysql_port", 0)
    server = start_bridge()
    try:
        with socket.create_connection(server.server_address, timeout=3) as client:
            assert client.recv(100) == b"MOCK_GREETING"
            payload = b"MOCK_ONLY\x00\xff" * 20000
            client.sendall(payload)
            received = bytearray()
            while len(received) < len(payload):
                received.extend(client.recv(65536))
            assert received == payload
    finally:
        upstream.close()
        server.shutdown()
        server.server_close()


def test_r2_gateway_restores_file_after_local_disk_loss(tmp_path, monkeypatch):
    objects = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_PUT(self):
            objects[self.path] = self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(204)
            self.end_headers()

        def do_GET(self):
            data = objects.get(self.path)
            self.send_response(200 if data is not None else 404)
            self.end_headers()
            if data is not None:
                self.wfile.write(data)

        def do_DELETE(self):
            objects.pop(self.path, None)
            self.send_response(204)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(
        settings, "storage_gateway", f"http://127.0.0.1:{server.server_port}"
    )
    path = tmp_path / "detail_uploads" / "mock.csv"
    path.parent.mkdir()
    path.write_bytes(b"MOCK_ONLY\x00\xff")
    try:
        storage.persist(path)
        path.unlink()
        assert storage.restore(path).read_bytes() == b"MOCK_ONLY\x00\xff"
        storage.remove(path)
        assert not objects
        with pytest.raises(HTTPException) as error:
            storage.restore(path)
        assert error.value.status_code == 410
    finally:
        server.shutdown()
        server.server_close()
