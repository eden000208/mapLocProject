from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8-sig", extra="ignore"
    )
    mysql_host: str = "10.44.225.184"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    app_database: str = "bsq_app"
    detail_database: str = ""
    datasource_path: Path = Path("datasource.yaml")
    data_dir: Path = Path("data")
    cookie_secure: bool = False
    session_idle_minutes: int = 30
    login_max_fail: int = 5
    login_lock_minutes: int = 15
    max_cells: int = Field(2000, ge=1, le=100000)
    max_months: int = Field(3, ge=1, le=24)
    max_rows: int = Field(200000, ge=1)
    cell_batch: int = Field(500, ge=1, le=1000)
    query_workers: int = Field(2, ge=1, le=10)
    query_queue: int = Field(10, ge=0)
    query_timeout_seconds: int = 600
    statement_timeout_seconds: int = 120
    result_ttl_hours: int = 24
    upload_max_mb: int = 30
    tianditu_key: str = ""
    map_center_lng: float = 112.20
    map_center_lat: float = 30.98
    map_zoom: int = 11
    min_draw_zoom: int = 12
    # Only used in the Cloudflare Container; local Compose keeps direct MySQL.
    cloudflare_mode: bool = False
    storage_gateway: str = ""
    mysql_bridge_url: str = ""

    def mysql_url(self, database: str | None = None) -> URL:
        return URL.create(
            "mysql+pymysql",
            username=self.mysql_user,
            password=self.mysql_password,
            host=self.mysql_host,
            port=self.mysql_port,
            database=database,
            query={"charset": "utf8mb4"},
        )


settings = Settings()
