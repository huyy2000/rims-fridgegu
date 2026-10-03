"""全局配置：从环境变量 / .env 读取，便于本地与云端切换。"""
import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 数据根目录：开发态 = backend/；打包后 = exe 所在目录（数据库/上传/配置都在这）
if getattr(sys, "frozen", False):
    APP_ROOT = Path(sys.executable).resolve().parent
else:
    APP_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "FridgePal"
    database_url: str = "sqlite:///./fridgepal.db"

    # LLM：mock（规则解析，无需 Key） | deepseek（真 LLM）
    llm_mode: str = "mock"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # ASR/TTS（阿里云百炼 DashScope）
    asr_mode: str = "mock"  # mock | dashscope
    dashscope_api_key: str = ""
    dashscope_asr_model: str = "paraformer-realtime-v2"
    dashscope_tts_model: str = "cosyvoice-v2"
    dashscope_tts_voice: str = "longxiaochun_v2"  # cosyvoice-v2 音色必须带 _v2 后缀
    dashscope_base_url: str = "https://dashscope.aliyuncs.com"

    # 微信（测试号阶段再填）
    wechat_appid: str = ""
    wechat_secret: str = ""
    wechat_token: str = ""

    # 设备鉴权用（后续改为正式签发机制）
    device_token_ttl_days: int = 365


settings = Settings()
