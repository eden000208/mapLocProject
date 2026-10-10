from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import zipfile

import pytest
from fastapi import HTTPException

from app import query
from app.models import utcnow


def task(**kwargs):
    values = dict(
        id="task",
        user_id=1,
        status="SUCCESS",
        cell_keys=[{"lac": 1, "cell_id": 2}],
        months=["202601"],
        nets=["local"],
        purpose='=HYPERLINK("invalid")',
        expire_at=utcnow() + timedelta(hours=1),
        rows_local=1,
        rows_other=0,
        uniq_local=1,
        uniq_other=0,
        completed_batches=1,
        total_batches=1,
        created_at=utcnow(),
        error="",
    )
    return SimpleNamespace(**(values | kwargs))


def test_masked_rows_exclude_uid_and_plain_is_explicit():
    row = SimpleNamespace(
        month_id="202601",
        uid="unit-only",
        device_number="13800000000",
        cell_name="A",
        street_name="B",
        cell_id=2,
        lac=1,
    )
    masked = query.row_payload(row, False)
    assert masked["device_number"] == "138****0000"
    assert "uid" not in masked
    assert query.row_payload(row, True)["uid"] == "unit-only"
    with pytest.raises(HTTPException) as caught:
        query.check_plain(SimpleNamespace(view_plain=False), True)
    assert caught.value.status_code == 403


def test_admin_plain_permission_and_task_ownership():
    admin = SimpleNamespace(id=1, role="admin", view_plain=False)
    query.check_plain(admin, True)
    db = MagicMock()
    db.get.return_value = task(user_id=2)
    with pytest.raises(HTTPException) as caught:
        query.authorized_task(db, admin, "task")
    assert caught.value.status_code == 404


def test_task_ownership_expiry_and_current_scope():
    db, user = MagicMock(), SimpleNamespace(id=1)
    db.get.return_value = task(user_id=2)
    with pytest.raises(HTTPException) as caught:
        query.authorized_task(db, user, "task")
    assert caught.value.status_code == 404
    db.get.return_value = task(expire_at=utcnow() - timedelta(seconds=1))
    with pytest.raises(HTTPException) as caught:
        query.authorized_task(db, user, "task")
    assert caught.value.status_code == 410
    db.get.return_value = task()
    with patch.object(query, "validate_cells", side_effect=HTTPException(403, "scope")):
        with pytest.raises(HTTPException) as caught:
            query.authorized_task(db, user, "task")
    assert caught.value.status_code == 403


def test_xlsx_formula_values_are_strings_and_three_sheets(tmp_path):
    db = MagicMock()
    db.scalars.side_effect = [
        [
            SimpleNamespace(
                month_id="202601",
                uid="unit-only",
                device_number="13800000000",
                cell_name="=1+1",
                street_name="B",
                cell_id=2,
                lac=1,
            )
        ],
        [],
    ]
    path = tmp_path / "export.xlsx"
    query.write_xlsx(db, task(), path, False)
    with zipfile.ZipFile(path) as archive:
        workbook = archive.read("xl/workbook.xml").decode()
        assert all(name in workbook for name in ("本网明细", "异网明细", "摘要"))
        for name in archive.namelist():
            if name.startswith("xl/worksheets/"):
                xml = archive.read(name).decode()
                assert "<f>" not in xml
                assert "unit-only" not in xml
        assert "138****0000" in archive.read("xl/worksheets/sheet1.xml").decode()


def test_failure_removes_partial_rows_and_resets_counts():
    db = MagicMock()
    failed = task()
    db.get.return_value = failed
    session = MagicMock()
    session.return_value.__enter__.return_value = db
    with patch.object(query, "SessionLocal", session):
        query.finish_failed("task", "cancelled", True)
    assert "DELETE FROM query_rows" in str(db.execute.call_args.args[0])
    assert failed.status == "CANCELLED"
    assert failed.rows_local == failed.rows_other == 0
    db.commit.assert_called_once()


def test_cancellation_and_total_timeout_checked():
    db = MagicMock()
    db.get.return_value = SimpleNamespace(cancel_requested=True)
    with patch.object(query._stop, "is_set", return_value=False):
        with pytest.raises(query.TaskInterrupted, match="取消"):
            query.check_running(db, "task", query.time.monotonic())
        with pytest.raises(query.TaskInterrupted, match="超时"):
            query.check_running(
                db,
                "task",
                query.time.monotonic() - query.settings.query_timeout_seconds - 1,
            )


def test_invalid_purpose_and_month_are_rejected():
    with pytest.raises(ValueError):
        query.QueryBody(
            cells=[{"lac": 1, "cell_id": 2}],
            months=["202601"],
            nets=["local"],
            purpose="  ",
        )


def test_other_plain_results_never_include_uid():
    row = SimpleNamespace(
        month_id="202601",
        uid="unit-only",
        device_number="13800000000",
        cell_name="A",
        street_name="B",
        cell_id=2,
        lac=1,
    )
    assert "uid" not in query.row_payload(row, True, include_uid=False)


def test_worker_row_limit_fails_and_releases_queue_slot():
    db = MagicMock()
    current_task = task(status="PENDING", user_id=1, cancel_requested=False)
    user = SimpleNamespace(id=1, is_active=True, role="analyst")
    db.get.side_effect = (
        lambda model, key: user if model is query.User else current_task
    )
    session = MagicMock()
    session.return_value.__enter__.return_value = db
    detail = dict(
        month_id="202601",
        uid=None,
        device_number="unit-only",
        cell_name=None,
        street_name=None,
        lac=1,
        cell_id=2,
    )
    slots = MagicMock()
    with (
        patch.object(query, "SessionLocal", session),
        patch.object(query, "validate_cells"),
        patch.object(query, "configured_sources", return_value={"local": {}}),
        patch.object(
            query,
            "stream_batch",
            side_effect=lambda *args: (value for value in [detail, detail]),
        ),
        patch.object(query, "check_running"),
        patch.object(query, "finish_failed") as failed,
        patch.object(query, "_slots", slots),
        patch.object(query.settings, "max_rows", 1),
        patch.object(query._stop, "is_set", return_value=False),
    ):
        query.run_task("task")
    assert "行数超过" in failed.call_args.args[1]
    assert failed.call_args.args[2] is False
    slots.release.assert_called_once()


def test_queue_is_bounded_by_workers_plus_waiting():
    with patch.object(query, "_executor", None), patch.object(query, "_slots", None):
        query.ensure_runtime()
        try:
            count = query.settings.query_workers + query.settings.query_queue
            assert all(query._slots.acquire(blocking=False) for _ in range(count))
            assert query._slots.acquire(blocking=False) is False
        finally:
            query._executor.shutdown(wait=True)
