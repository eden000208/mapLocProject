from unittest.mock import MagicMock, patch

import pytest

from app import datasource


SOURCE = {
    "table": "detail.local_calls",
    "fields": {
        "month_id": "month_id",
        "device_number": "phone",
        "lac": "lac",
        "cell_id": "cell_id",
    },
}


def test_identifiers_are_quoted_and_injection_rejected():
    assert datasource.quote_identifier("db.table") == "`db`.`table`"
    for value in ("a;DROP", "a..b", "a`", "a b", None):
        with pytest.raises(datasource.SourceUnavailable):
            datasource.quote_identifier(value)


def test_statement_uses_bound_values_and_optional_null_columns():
    statement, params = datasource.build_statement(
        SOURCE, "2026' OR 1=1", [{"lac": 1, "cell_id": 2}], 11
    )
    sql = str(statement)
    assert "2026'" not in sql
    assert "NULL AS `uid`" in sql
    assert "LIMIT :row_limit" in sql
    assert params == {"month": "2026' OR 1=1", "row_limit": 11, "lac_0": 1, "cell_0": 2}


def test_load_columns_mapping_and_unconfigured_sources(tmp_path):
    path = tmp_path / "mapping.yaml"
    path.write_text(
        "sources:\n  local:\n    table: details.calls\n    columns:\n"
        "      month_id: month_id\n      device_number: phone\n"
        "      lac: lac\n      cell_id: cell\n",
        encoding="utf-8",
    )
    with patch.object(datasource.settings, "datasource_path", path):
        assert datasource.load_sources()["local"]["fields"]["device_number"] == "phone"
        with pytest.raises(datasource.SourceUnavailable):
            datasource.configured_sources(["other"])


def test_months_combines_actual_sources():
    conn = MagicMock()
    conn.execute.side_effect = [[("202601",), ("202602",)], [("202602",), ("202603",)]]
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    with (
        patch.object(
            datasource,
            "configured_sources",
            return_value={
                "local": SOURCE,
                "other": SOURCE,
            },
        ),
        patch.object(datasource, "detail_engine", return_value=engine),
    ):
        assert datasource.available_months(["local", "other"]) == [
            "202603",
            "202602",
            "202601",
        ]
