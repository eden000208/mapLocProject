from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app import demo


def test_cleanup_rejects_other_database(monkeypatch):
    monkeypatch.setattr(demo.settings, "app_database", "other")
    session = MagicMock()
    monkeypatch.setattr(demo, "SessionLocal", session)
    with pytest.raises(ValueError, match="bsq_app"):
        demo.cleanup_demo()
    session.assert_not_called()


def test_cleanup_rejects_non_demo_reserved_station(monkeypatch):
    db = MagicMock()
    db.scalar.return_value = None
    db.scalars.return_value = [
        SimpleNamespace(lac=demo.LAC, cell_id=1, station_name="业务站点")
    ]
    monkeypatch.setattr(demo, "SessionLocal", lambda: db)
    db.__enter__.return_value = db
    with pytest.raises(ValueError, match="非模拟数据"):
        demo.cleanup_demo()
    db.execute.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize("status,mixed", [("RUNNING", False), ("SUCCESS", True)])
def test_cleanup_rejects_running_and_mixed_tasks(monkeypatch, status, mixed):
    db = MagicMock()
    db.__enter__.return_value = db
    db.scalar.return_value = None
    keys = [{"lac": demo.LAC, "cell_id": 1}]
    if mixed:
        keys.append({"lac": 1, "cell_id": 1})
    db.scalars.side_effect = [[], [SimpleNamespace(cell_keys=keys, status=status)]]
    monkeypatch.setattr(demo, "SessionLocal", lambda: db)
    with pytest.raises(ValueError):
        demo.cleanup_demo()
    db.execute.assert_not_called()
    db.commit.assert_not_called()


def test_cleanup_only_deletes_marked_details_and_demo_files(monkeypatch, tmp_path):
    db = MagicMock()
    db.__enter__.return_value = db
    db.scalar.return_value = None
    db.scalars.side_effect = [[], []]
    db.execute.return_value.rowcount = 0
    monkeypatch.setattr(demo, "SessionLocal", lambda: db)
    monkeypatch.setattr(demo.settings, "data_dir", tmp_path)
    for name in ("demo-login.json", "acceptance.json", "initial-admin.txt"):
        (tmp_path / name).write_text("placeholder", encoding="utf-8")
    report = demo.cleanup_demo()
    assert report["stations"] == report["tasks"] == report["users"] == 0
    assert (tmp_path / "initial-admin.txt").exists()
    assert not (tmp_path / "demo-login.json").exists()
    statements = [str(call.args[0]) for call in db.execute.call_args_list]
    assert len(statements) == 2
    assert all("is_demo IS true" in sql for sql in statements)
    db.commit.assert_called_once()
