"""只读检查表结构，不输出凭据或业务明细。"""

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from .config import settings


def main() -> None:
    engine = create_engine(settings.mysql_url(), connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as conn:
            print("MySQL:", conn.scalar(text("SELECT VERSION()")))
            rows = conn.execute(
                text(
                    "SELECT table_schema, table_name, "
                    "GROUP_CONCAT(column_name ORDER BY ordinal_position) AS cols "
                    "FROM information_schema.columns WHERE table_schema NOT IN "
                    "('mysql','sys','performance_schema','information_schema') "
                    "GROUP BY table_schema, table_name"
                )
            )
            found = False
            for schema, table, cols in rows:
                if any(
                    c in cols.lower().split(",")
                    for c in ("month_id", "device_number", "lac", "cell_id")
                ):
                    print(f"{schema}.{table}: {cols}")
                    found = True
            if not found:
                print("未找到采用默认字段名的明细表；请配置真实字段映射。")
    except DBAPIError as exc:
        code = getattr(exc.orig, "args", (None,))[0]
        raise SystemExit(
            f"连接失败：MySQL错误码 {code}，目标 "
            f"{settings.mysql_host}:{settings.mysql_port}，用户 {settings.mysql_user}。"
            "检查密码及客户端权限；1045 表示认证被拒绝。"
        ) from None
    except Exception:
        raise SystemExit("连接失败：检查 MySQL 用户、密码和客户端访问权限。") from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
