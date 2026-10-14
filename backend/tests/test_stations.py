from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from shapely.geometry import Point
from shapely.strtree import STRtree

from app.dto.stations import PreviewBody, SelectionBody
from app.models import Station
from app.services import stations


def test_import_duplicates_and_errors():
    headers = list(stations.FIELDS)
    rows = [
        ["1", "2", "first", "D", "", "112", "31"],
        ["1", "2", "last", "D", "", "112", "31"],
        ["3", "4", "unscoped", "", "", "112", "31"],
        ["5", "6", "bad", "D", "", "nan", "31"],
    ]
    valid, errors, warnings = stations.parse_rows(
        headers, rows, {k: k for k in headers}, "WGS84"
    )
    assert len(valid) == 2 and valid[0]["station_name"] == "last"
    assert errors[0]["row"] == 5
    assert warnings[0]["row"] == 3
    assert warnings[1]["row"] == 4


def test_original_headers_aliases():
    assert "REST_LONGITUDE" in stations.ALIASES["lng"]
    assert "REST_LATITUDE" in stations.ALIASES["lat"]
    assert "CI" in stations.ALIASES["cell_id"]
    assert "基站归属区县" in stations.ALIASES["district"]
    assert "基站归属营服" in stations.ALIASES["service_center"]


def test_preview_coord_keys_interpret_raw(monkeypatch):
    headers = list(stations.FIELDS)
    rows = [["1", "2", "A", "D", "", "112.2", "30.98"]]
    batch = SimpleNamespace(status="UPLOADED", path="unused", preview=None)
    monkeypatch.setattr(stations, "own_batch", lambda *args: batch)
    monkeypatch.setattr(stations, "read_upload", lambda path: (headers, rows))
    db = MagicMock()
    db.scalar.return_value = 0
    result = stations.preview(
        "batch",
        PreviewBody(mapping={k: k for k in headers}, coord_sys="GCJ02"),
        SimpleNamespace(id=1),
        db,
    )
    point = result["points"][0]
    assert point["WGS84"] == point["raw"]
    assert point["GCJ02"] == list(stations.to_wgs(*point["raw"], "GCJ02"))
    assert point["BD09"] == list(stations.to_wgs(*point["raw"], "BD09"))


def test_integer_precision_and_invalid():
    assert stations.parse_integer("9223372036854775807") == 9223372036854775807
    for value in ("1.1", "nan", "-1", "9223372036854775808"):
        with pytest.raises(ValueError):
            stations.parse_integer(value)


def test_validate_cells_denies_scope():
    station = Station(lac=1, cell_id=2, district="D", service_center="", is_active=True)
    db = MagicMock()
    db.scalars.return_value = [station]
    user = SimpleNamespace(role="analyst", districts=[], service_centers=[])
    with pytest.raises(HTTPException) as exc:
        stations.validate_cells(db, user, [{"lac": 1, "cell_id": 2}])
    assert exc.value.status_code == 403


def test_polygon_includes_boundary_and_filters(monkeypatch):
    rows = [
        {
            "lac": 1,
            "cell_id": 2,
            "station_name": "A",
            "district": "D",
            "service_center": "",
            "lng": 112,
            "lat": 31,
        },
        {
            "lac": 1,
            "cell_id": 3,
            "station_name": "B",
            "district": "OTHER",
            "service_center": "",
            "lng": 112.5,
            "lat": 31.5,
        },
    ]
    monkeypatch.setattr(
        stations,
        "get_index",
        lambda db: (rows, STRtree([Point(r["lng"], r["lat"]) for r in rows])),
    )
    body = SelectionBody(
        type="polygon",
        geometry={
            "type": "Polygon",
            "coordinates": [[[112, 31], [113, 31], [113, 32], [112, 32], [112, 31]]],
        },
    )
    response = stations.resolve(
        body,
        SimpleNamespace(role="analyst", districts=["D"], service_centers=[]),
        MagicMock(),
    )
    assert response["cell_count"] == 1
    assert response["excluded_count"] == 1


def test_admin_can_validate_any_active_station():
    station = Station(
        lac=1, cell_id=2, district="OTHER", service_center="", is_active=True
    )
    db = MagicMock()
    db.scalars.return_value = [station]
    user = SimpleNamespace(role="admin", districts=[], service_centers=[])
    assert stations.validate_cells(db, user, [{"lac": 1, "cell_id": 2}]) == [station]
    station.is_active = False
    with pytest.raises(HTTPException) as exc:
        stations.validate_cells(db, user, [{"lac": 1, "cell_id": 2}])
    assert exc.value.status_code == 422


def test_admin_map_includes_unscoped_station(monkeypatch):
    row = {
        "lac": 1,
        "cell_id": 2,
        "station_name": "A",
        "district": "",
        "service_center": "",
        "lng": 112,
        "lat": 31,
    }
    monkeypatch.setattr(
        stations, "get_index", lambda db: ([row], STRtree([Point(112, 31)]))
    )
    admin = SimpleNamespace(role="admin", districts=[], service_centers=[])
    analyst = SimpleNamespace(role="analyst", districts=[], service_centers=[])
    assert stations.map_stations("111,30,113,32", 12, "", admin, MagicMock())["items"][
        0
    ]["cells"] == [row]
    assert (
        stations.map_stations("111,30,113,32", 12, "", analyst, MagicMock())["items"]
        == []
    )


def test_csv_formula_escape():
    response = stations.csv_response([["=1+1", "safe"]], "errors.csv")
    assert "'=1+1" in response.body.decode()


def test_confirm_is_idempotent(monkeypatch):
    batch = SimpleNamespace(
        status="CONFIRMED", preview={"confirmed": {"imported": 2, "error_count": 0}}
    )
    monkeypatch.setattr(stations, "own_batch", lambda *args: batch)
    db = MagicMock()
    result = stations.confirm("same-batch", SimpleNamespace(id=1), db)
    assert result["imported"] == 2
    db.execute.assert_not_called()


def test_chinese_template_and_coordinate_errors():
    headers = list(stations.LABELS.values())
    mapping = dict(zip(stations.FIELDS, headers))
    valid, errors, _ = stations.parse_rows(
        headers, [[1, 2, "站点", "区县", "营服", "不是数字", 31]], mapping, "WGS84"
    )
    assert not valid
    assert "经度必须填写数字" in errors[0]["message"]
    assert "不是数字" not in errors[0]["message"]
    assert "基站名称" in stations.template(None).body.decode("utf-8-sig")
    with pytest.raises(HTTPException) as exc:
        stations.parse_rows(headers, [], {}, "WGS84")
    assert "经度" in exc.value.detail
