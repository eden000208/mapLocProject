import io
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient

from app.services import detail_upload as module
from app.dependencies import current_user
from app.main import app
from app.models import utcnow


def sample(tmp_path, body="202610,DEMO_ONLY_NUMBER,A,B,1,2\n"):
    path = tmp_path / "sample.csv"
    path.write_text(",".join(module.FIELDS) + "\n" + body, encoding="utf-8-sig")
    return path


def batch(path, valid=True):
    return SimpleNamespace(
        id="batch",
        user_id=1,
        filename="detail:other",
        path=str(path),
        status="DETAIL_PREVIEWED",
        created_at=utcnow(),
        preview={"network": "other", "valid": valid, "months": ["202610"]},
    )


def test_multiple_months_and_safe_errors(tmp_path):
    path = sample(
        tmp_path, "202610,DEMO_ONLY_NUMBER,A,B,1,2\n202611,DEMO_ONLY_NUMBER,A,B,1,2\n"
    )
    result = module.scan_file(path, "other")
    assert result["months"] == ["202610", "202611"]
    assert result["rows"] == 2 and result["valid"]
    path = sample(tmp_path, "202613,DEMO_ONLY_NUMBER,A,B,1,2\n")
    result = module.scan_file(path, "other")
    assert result["error_count"] == 1
    assert "DEMO_ONLY_NUMBER" not in str(result)


@pytest.mark.parametrize(
    "body",
    [
        "202610,,A,B,1,2\n",
        "202610,DEMO_ONLY_NUMBER,A,B,-1,2\n",
        "202610,DEMO_ONLY_NUMBER,A,B,1,9223372036854775808\n",
        "202610,DEMO_ONLY_NUMBER,A,B,1\n",
    ],
)
def test_invalid_rows(tmp_path, body):
    assert not module.scan_file(sample(tmp_path, body), "other")["valid"]


def test_duplicate_headers_rejected(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("month_id,month_id\n202610,202610\n")
    with pytest.raises(HTTPException):
        module.scan_file(path, "other")


def test_existing_month_rejects_before_insert(tmp_path, monkeypatch):
    db = MagicMock()
    db.scalar.return_value = batch(sample(tmp_path))
    monkeypatch.setattr(module, "target_table", lambda net: module.other_table)
    monkeypatch.setattr(module, "existing_months", lambda *a, **kw: ["202610"])
    with pytest.raises(HTTPException) as exc:
        module.write_batch(db, "batch", SimpleNamespace(id=1))
    assert exc.value.status_code == 409
    db.execute.assert_not_called()
    db.commit.assert_not_called()


def test_success_single_commit_and_no_sensitive_audit(tmp_path, monkeypatch):
    db = MagicMock()
    record = batch(sample(tmp_path))
    db.scalar.return_value = record
    monkeypatch.setattr(module, "target_table", lambda net: module.other_table)
    monkeypatch.setattr(module, "existing_months", lambda *a, **kw: [])
    audit = MagicMock()
    monkeypatch.setattr(module, "log_event", audit)
    result = module.write_batch(db, "batch", SimpleNamespace(id=1))
    assert result["imported"] == 1
    assert record.status == "DETAIL_CONFIRMED"
    db.commit.assert_called_once()
    assert "DEMO_ONLY_NUMBER" not in str(audit.call_args)


def test_failed_insert_never_commits(tmp_path, monkeypatch):
    db = MagicMock()
    db.scalar.return_value = batch(sample(tmp_path))
    db.execute.side_effect = RuntimeError("synthetic failure")
    monkeypatch.setattr(module, "target_table", lambda net: module.other_table)
    monkeypatch.setattr(module, "existing_months", lambda *a, **kw: [])
    with pytest.raises(RuntimeError):
        module.write_batch(db, "batch", SimpleNamespace(id=1))
    db.commit.assert_not_called()


def test_ownership_and_repeat_rejected(tmp_path):
    db = MagicMock()
    record = batch(sample(tmp_path))
    db.scalar.return_value = record
    with pytest.raises(HTTPException) as exc:
        module.own_batch(db, "batch", SimpleNamespace(id=2))
    assert exc.value.status_code == 404
    record.status = "DETAIL_CONFIRMED"
    with pytest.raises(HTTPException):
        module.write_batch(db, "batch", SimpleNamespace(id=1))


def test_size_limit_removes_partial_file(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "MAX_BYTES", 5)
    monkeypatch.setattr(module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(module, "target_table", lambda net: module.other_table)
    monkeypatch.setattr(module, "clean_expired", lambda db: None)
    with pytest.raises(HTTPException) as exc:
        module.upload(
            UploadFile(filename="test.csv", file=io.BytesIO(b"123456")),
            "other",
            SimpleNamespace(id=1),
            MagicMock(),
        )
    assert exc.value.status_code == 413
    assert not list((tmp_path / "detail_uploads").iterdir())


def test_analyst_denied_on_all_endpoints():
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(role="analyst")
    try:
        client = TestClient(app)
        for url in (
            "/api/admin/detail-import",
            "/api/admin/detail-import/x/preview",
            "/api/admin/detail-import/x/confirm",
        ):
            response = client.post(
                url, data={"network": "other"}, files={"file": ("a.csv", b"test")}
            )
            assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_gb18030_and_xlsx_reader(tmp_path):
    path = sample(tmp_path)
    path.write_bytes(
        path.read_text(encoding="utf-8-sig").replace("A", "模拟小区").encode("gb18030")
    )
    assert module.scan_file(path, "other")["valid"]
    # 用 mock 工作簿验证只读迭代及资源释放，不新增任何类。
    from unittest.mock import patch

    book = MagicMock()
    book.worksheets = [book.active]
    book.active.iter_rows.return_value = iter(
        [
            module.FIELDS,
            (202610, "DEMO_ONLY_NUMBER", "A", "B", 1, 2),
        ]
    )
    with patch.object(module, "load_workbook", return_value=book):
        assert module.scan_file(tmp_path / "a.xlsx", "other")["valid"]
    book.close.assert_called_once()


def test_confirm_failure_rolls_back_and_releases_lock(tmp_path, monkeypatch):
    db = MagicMock()
    record = batch(sample(tmp_path))
    db.scalar.return_value = record
    connection = MagicMock()
    connection.scalar.return_value = 1
    connect = MagicMock()
    connect.connect.return_value.__enter__.return_value = connection
    writer = MagicMock()
    writer_context = MagicMock()
    writer_context.__enter__.return_value = writer

    def close_writer(*args):
        writer.rollback()
        return False

    writer_context.__exit__.side_effect = close_writer
    monkeypatch.setattr(module, "engine", connect)
    monkeypatch.setattr(module, "Session", lambda **kw: writer_context)
    monkeypatch.setattr(module, "target_table", lambda net: module.other_table)
    monkeypatch.setattr(
        module, "write_batch", MagicMock(side_effect=RuntimeError("failure"))
    )
    with pytest.raises(RuntimeError):
        module.confirm("batch", SimpleNamespace(id=1), db)
    writer.rollback.assert_called_once()
    connection.rollback.assert_called_once()
    assert "RELEASE_LOCK" in str(connection.execute.call_args.args[0])
    assert sample(tmp_path).exists()


def test_busy_network_rejected(tmp_path, monkeypatch):
    db = MagicMock()
    db.scalar.return_value = batch(sample(tmp_path))
    connection = MagicMock()
    connection.scalar.return_value = 0
    connect = MagicMock()
    connect.connect.return_value.__enter__.return_value = connection
    monkeypatch.setattr(module, "engine", connect)
    monkeypatch.setattr(module, "target_table", lambda net: module.other_table)
    with pytest.raises(HTTPException) as exc:
        module.confirm("batch", SimpleNamespace(id=1), db)
    assert exc.value.status_code == 409
