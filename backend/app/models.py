from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(100), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="analyst")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    view_plain: Mapped[bool] = mapped_column(Boolean, default=False)
    districts: Mapped[list] = mapped_column(JSON, default=list)
    service_centers: Mapped[list] = mapped_column(JSON, default=list)
    must_change_pwd: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_count: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    last_seen: Mapped[datetime] = mapped_column(default=utcnow)


class Station(Base):
    __tablename__ = "stations"
    __table_args__ = (
        UniqueConstraint("lac", "cell_id", name="uq_station_cell"),
        Index("ix_station_coords", "lng", "lat"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    lac: Mapped[int] = mapped_column(BigInteger)
    cell_id: Mapped[int] = mapped_column(BigInteger)
    station_name: Mapped[str] = mapped_column(String(200), default="")
    district: Mapped[str] = mapped_column(String(100), default="", index=True)
    service_center: Mapped[str] = mapped_column(String(100), default="", index=True)
    lng: Mapped[float] = mapped_column(Float)
    lat: Mapped[float] = mapped_column(Float)
    lng_raw: Mapped[float] = mapped_column(Float)
    lat_raw: Mapped[float] = mapped_column(Float)
    coord_sys: Mapped[str] = mapped_column(String(16), default="WGS84")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="UPLOADED")
    preview: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class QueryTask(Base):
    __tablename__ = "query_tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    cell_keys: Mapped[list] = mapped_column(JSON)
    months: Mapped[list] = mapped_column(JSON)
    nets: Mapped[list] = mapped_column(JSON)
    purpose: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    rows_local: Mapped[int] = mapped_column(default=0)
    rows_other: Mapped[int] = mapped_column(default=0)
    uniq_local: Mapped[int] = mapped_column(default=0)
    uniq_other: Mapped[int] = mapped_column(default=0)
    completed_batches: Mapped[int] = mapped_column(default=0)
    total_batches: Mapped[int] = mapped_column(default=0)
    error: Mapped[str] = mapped_column(String(250), default="")
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expire_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class QueryRow(Base):
    __tablename__ = "query_rows"
    __table_args__ = (Index("ix_rows_task_net_id", "task_id", "net", "id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("query_tasks.id"))
    net: Mapped[str] = mapped_column(String(8))
    month_id: Mapped[str] = mapped_column(String(16))
    uid: Mapped[str | None] = mapped_column(String(200), nullable=True)
    device_number: Mapped[str] = mapped_column(String(100))
    cell_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    street_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cell_id: Mapped[int] = mapped_column(BigInteger)
    lac: Mapped[int] = mapped_column(BigInteger)


class OperationLog(Base):
    __tablename__ = "operation_logs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
