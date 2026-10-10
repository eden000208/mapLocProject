"""显式创建 bsq_app 明细表；在线查询保持只读。"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Index,
    MetaData,
    String,
    Table,
)

from .config import settings
from .db import engine

metadata = MetaData()


def detail_table(name: str, local: bool) -> Table:
    columns = [
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column("month_id", String(16), nullable=False),
        Column("device_number", String(100), nullable=False),
        Column("cell_name", String(255)),
        Column("street_name", String(255)),
        Column("lac", BigInteger, nullable=False),
        Column("cell_id", BigInteger, nullable=False),
        Column("is_demo", Boolean, nullable=False, server_default="0"),
    ]
    if local:
        columns.append(Column("uid", String(200)))
    return Table(
        name,
        metadata,
        *columns,
        Index(f"ix_{name}_month_cell", "month_id", "lac", "cell_id"),
        mysql_charset="utf8mb4",
    )


local_table = detail_table("detail_local", True)
other_table = detail_table("detail_other", False)


def create_detail_tables() -> None:
    if settings.app_database != "bsq_app":
        raise ValueError("Owned detail initialization is restricted to bsq_app")
    metadata.create_all(engine)
