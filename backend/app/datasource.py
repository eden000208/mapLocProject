"""按白名单配置只读访问明细表。"""

import re
from functools import lru_cache

import yaml
from sqlalchemy import create_engine, text

from .config import settings

FIELDS = (
    "month_id",
    "uid",
    "device_number",
    "cell_name",
    "street_name",
    "cell_id",
    "lac",
)
REQUIRED = {"month_id", "device_number", "cell_id", "lac"}
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SourceUnavailable(ValueError):
    pass


def quote_identifier(value: str) -> str:
    if not isinstance(value, str) or not all(
        IDENTIFIER.fullmatch(part) for part in value.split(".")
    ):
        raise SourceUnavailable("Invalid configured SQL identifier")
    return ".".join(f"`{part}`" for part in value.split("."))


def load_sources() -> dict:
    try:
        data = yaml.safe_load(settings.datasource_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SourceUnavailable("Detail mapping is not configured") from exc
    if not isinstance(data, dict):
        raise SourceUnavailable("Invalid detail mapping")
    data = data.get("sources", data)
    if not isinstance(data, dict):
        raise SourceUnavailable("Invalid detail mapping")
    sources = {}
    for net in ("local", "other"):
        source = data.get(net)
        if not source:
            continue
        if not isinstance(source, dict):
            raise SourceUnavailable("Invalid detail mapping")
        if not source.get("table"):
            continue
        source = dict(source)
        source["fields"] = source.get("fields", source.get("columns"))
        if not isinstance(source["fields"], dict):
            raise SourceUnavailable("Invalid detail mapping")
        quote_identifier(source.get("table"))
        fields = source["fields"]
        if not REQUIRED.issubset(fields) or not all(fields[key] for key in REQUIRED):
            raise SourceUnavailable("Required detail field mapping is missing")
        for key, value in fields.items():
            if key not in FIELDS:
                raise SourceUnavailable("Unknown configured detail field")
            if value is not None:
                quote_identifier(value)
        sources[net] = source
    return sources


@lru_cache(maxsize=1)
def detail_engine():
    return create_engine(
        settings.mysql_url(settings.detail_database or None),
        pool_pre_ping=True,
        pool_size=settings.query_workers + 1,
        max_overflow=1,
        connect_args={
            "connect_timeout": 5,
            "read_timeout": max(1, settings.statement_timeout_seconds),
        },
    )


def configured_sources(nets: list[str]) -> dict:
    sources = load_sources()
    if any(net not in sources for net in nets):
        raise SourceUnavailable("Requested detail source is not configured")
    return {net: sources[net] for net in nets}


def timeout_hint() -> str:
    milliseconds = max(1, int(settings.statement_timeout_seconds * 1000))
    return f"/*+ MAX_EXECUTION_TIME({milliseconds}) */"


def available_months(nets: list[str]) -> list[str]:
    values = set()
    for source in configured_sources(nets).values():
        month = quote_identifier(source["fields"]["month_id"])
        table = quote_identifier(source["table"])
        statement = text(
            f"SELECT {timeout_hint()} DISTINCT {month} AS month_id "
            f"FROM {table} WHERE {month} IS NOT NULL ORDER BY {month} DESC LIMIT 1000"
        )
        with detail_engine().connect() as connection:
            values.update(str(row[0]) for row in connection.execute(statement))
    return sorted(values, reverse=True)


def build_statement(source: dict, month: str, cells: list[dict], limit: int):
    if not cells:
        raise ValueError("Cells must not be empty")
    fields = source["fields"]
    projections = []
    for key in FIELDS:
        value = fields.get(key)
        expression = quote_identifier(value) if value else "NULL"
        projections.append(f"{expression} AS `{key}`")
    predicates = []
    params = {"month": month, "row_limit": limit}
    lac = quote_identifier(fields["lac"])
    cell_id = quote_identifier(fields["cell_id"])
    for index, cell in enumerate(cells):
        predicates.append(f"({lac} = :lac_{index} AND {cell_id} = :cell_{index})")
        params[f"lac_{index}"] = cell["lac"]
        params[f"cell_{index}"] = cell["cell_id"]
    statement = text(
        f"SELECT {timeout_hint()} {', '.join(projections)} "
        f"FROM {quote_identifier(source['table'])} "
        f"WHERE {quote_identifier(fields['month_id'])} = :month "
        f"AND ({' OR '.join(predicates)}) LIMIT :row_limit"
    )
    return statement, params


def stream_batch(source: dict, month: str, cells: list[dict], limit: int):
    statement, params = build_statement(source, month, cells, limit)
    with detail_engine().connect().execution_options(stream_results=True) as conn:
        result = conn.execute(statement, params).mappings()
        try:
            for row in result:
                yield dict(row)
        finally:
            result.close()
