# -*- coding: utf-8 -*-
"""冰箱菇后台管理系统 · 启动器。

双击运行（打包后的 fridgegu-admin.exe）：
  1. 数据（数据库/上传/配置）落在 exe 同目录，便于备份与迁移；
  2. 启动后端服务（端口默认 8000，可用环境变量 FRIDGE_GU_PORT 覆盖）；
  3. 自动打开管理界面（浏览器）；
  4. 关闭本窗口 = 停止后台服务。
"""
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
    os.chdir(ROOT)  # 让 .env / 相对路径都以 exe 目录为准
    os.environ.setdefault(
        "DATABASE_URL", "sqlite:///" + str(ROOT / "fridgepal.db").replace("\\", "/")
    )

PORT = int(os.environ.get("FRIDGE_GU_PORT", "8000"))

try:
    import ctypes

    ctypes.windll.kernel32.SetConsoleTitleW(f"冰箱菇后台管理系统 · 端口 {PORT}")
except Exception:
    pass

BANNER = r"""
  ┌─────────────────────────────────────────────┐
  │   🍄 冰箱菇 后台管理系统  RIMS · FridgePal   │
  │   管理界面  http://127.0.0.1:%d/web/      │
  │   微信回调  /api/v1/wechat/callback         │
  │   数据目录  %s
  │   关闭本窗口即停止服务                        │
  └─────────────────────────────────────────────┘""" % (
    PORT,
    str(Path.cwd())[:34],
)


def _open_browser_later():
    time.sleep(2.0)
    webbrowser.open(f"http://127.0.0.1:{PORT}/web/")


def main():
    print(BANNER)
    threading.Thread(target=_open_browser_later, daemon=True).start()

    from app.main import app  # noqa: E402  （依赖 CWD/.env 已就位后再导入）
    import uvicorn  # noqa: E402

    uvicorn.run(app, host="0.0.0.0", port=PORT, log_config=None)


if __name__ == "__main__":
    main()
