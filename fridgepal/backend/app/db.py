"""数据库连接与会话管理。

开发默认 SQLite（零安装）；上线前通过环境变量 DATABASE_URL 切到 PostgreSQL，
代码无需改动（SQLAlchemy 统一抽象）。
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

_connect_args = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI 依赖：每个请求一个会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """开发期直接建表；上线前换成 Alembic 迁移。"""
    from . import models  # noqa: F401  确保模型注册

    Base.metadata.create_all(bind=engine)
