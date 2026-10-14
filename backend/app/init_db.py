"""初始化 bsq_app 系统表和明细表，不修改其他数据库。"""

import getpass
import re

from sqlalchemy import create_engine, select, text

from . import models
from .services.auth import hash_password
from .config import settings
from .db import Base, SessionLocal, engine
from .detail_schema import create_detail_tables


def main() -> None:
    name = settings.app_database
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name):
        raise SystemExit("APP_DATABASE 名称不合法")
    server = create_engine(settings.mysql_url(), pool_pre_ping=True)
    try:
        with server.begin() as conn:
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
        Base.metadata.create_all(engine)
        create_detail_tables()
        with SessionLocal() as db:
            exists = db.scalar(
                select(models.User.id).where(
                    models.User.role == "admin", models.User.is_active.is_(True)
                )
            )
            if exists:
                print("系统表已就绪，已有管理员；未修改账号。")
                return
            username = input("初始管理员用户名 [admin]: ").strip() or "admin"
            password = getpass.getpass("管理员密码（至少10位，包含字母和数字）: ")
            if (
                len(password) < 10
                or not any(c.isalpha() for c in password)
                or not any(c.isdigit() for c in password)
            ):
                raise SystemExit("密码不符合要求")
            if password != getpass.getpass("再次输入密码: "):
                raise SystemExit("两次输入不一致")
            db.add(
                models.User(
                    username=username,
                    name="管理员",
                    role="admin",
                    password_hash=hash_password(password),
                    must_change_pwd=True,
                )
            )
            db.commit()
        print("系统库初始化完成。")
    except Exception:
        raise SystemExit(
            "初始化失败：请检查 MySQL 连接、建库建表权限及账号名是否重复。"
        ) from None
    finally:
        server.dispose()


if __name__ == "__main__":
    main()
