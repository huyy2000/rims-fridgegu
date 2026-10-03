"""初始化数据库（开发期用 create_all；上线前换 Alembic 迁移）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.db import init_db  # noqa: E402

if __name__ == "__main__":
    init_db()
    print("数据库初始化完成 ✅")
