"""FridgePal 后端入口。

启动：uvicorn app.main:app --reload
文档：http://127.0.0.1:8000/docs
"""
from contextlib import asynccontextmanager
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings, APP_ROOT
from .db import init_db
from .api import ai, device, hotwords, inventory, recordings, shopping, wechat

# web 静态资源：打包后在 _internal/web，开发态在 fridgepal/web
if getattr(sys, "frozen", False):
    _WEB_DIR = Path(sys._MEIPASS) / "web"
else:
    _WEB_DIR = APP_ROOT.parent / "web"
_UPLOADS_DIR = APP_ROOT / "uploads"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    from .services import dashscope_service

    dashscope_service.ensure_dirs()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description="冰箱菇（RIMS）云端后端：录音→ASR→LLM→库存→公众号卡片",
    lifespan=lifespan,
)

# 开发期放开跨域；上线前收敛为 H5 域名白名单
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (device.router, inventory.router, shopping.router, ai.router,
          recordings.router, hotwords.router, wechat.router):
    app.include_router(r, prefix="/api/v1")

# 展示软件（静态站）与上传文件
if _WEB_DIR.exists():
    app.mount("/web", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_UPLOADS_DIR)), name="uploads")


@app.get("/")
def index():
    from fastapi.responses import RedirectResponse

    return RedirectResponse("/web/")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "llm_mode": settings.llm_mode,
        "asr_mode": settings.asr_mode,
    }
