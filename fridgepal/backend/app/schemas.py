"""请求/响应模型（Pydantic）。"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------- 设备 ----------

class DeviceRegisterRequest(BaseModel):
    device_sn: str = Field(..., min_length=1, max_length=64)
    device_type: str = "base"
    mac_address: Optional[str] = None
    firmware_version: Optional[str] = None


class DeviceRegisterResponse(BaseModel):
    device_id: str
    device_token: str


class DeviceBindRequest(BaseModel):
    device_id: str
    user_id: str
    device_token: str


class DeviceHeartbeatRequest(BaseModel):
    device_id: str
    device_token: str
    battery: Optional[int] = None
    muted: Optional[bool] = None
    door_open: Optional[bool] = None


# ---------- 库存 ----------

class InventoryOut(BaseModel):
    id: str
    item_name: str
    category: str
    quantity: float
    unit: str
    location: str
    expire_at: Optional[datetime] = None
    status: str
    added_at: datetime

    model_config = {"from_attributes": True}


class InventoryCreate(BaseModel):
    """手动入库（H5 用）；location 不填 = 按常识库自动推断"""
    item_name: str
    category: str = "其他"
    quantity: float = 1
    unit: str = "个"
    location: Optional[str] = None
    expire_days: Optional[int] = None


class InventoryUpdate(BaseModel):
    item_name: Optional[str] = None
    category: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    location: Optional[str] = None
    status: Optional[str] = None


# ---------- 购物清单 ----------

class ShoppingItemCreate(BaseModel):
    item_name: str
    category: Optional[str] = None
    quantity: str = "1"


class ShoppingItemOut(BaseModel):
    id: str
    item_name: str
    category: Optional[str]
    quantity: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- AI 对话 ----------

class ChatRequest(BaseModel):
    user_id: str
    channel: str = "voice"  # voice | wechat
    text: str
    context: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    reply_text: str
    display_text: Optional[str] = None
    tts_url: Optional[str] = None
    actions: list[dict[str, Any]] = Field(default_factory=list)
