"""数据模型（对应开发计划 §四 数据库设计，开发期简化）。

说明：
- 主键用 UUID 字符串（与计划一致，避免前端/日志处理二进制 UUID 的麻烦）。
- 时间统一 UTC。
- 分类/单位用中文枚举值，后续对齐英文 code。
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    wechat_openid: Mapped[str | None] = mapped_column(
        String(128), unique=True, index=True
    )
    nickname: Mapped[str | None] = mapped_column(String(64))
    phone: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    device_sn: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    device_name: Mapped[str] = mapped_column(String(64), default="我的冰箱贴")
    device_type: Mapped[str] = mapped_column(String(16), default="base")  # base | mic
    parent_device_id: Mapped[str | None] = mapped_column(String(36))
    firmware_version: Mapped[str | None] = mapped_column(String(16))
    mac_address: Mapped[str | None] = mapped_column(String(17))
    device_token: Mapped[str] = mapped_column(String(64), default=gen_uuid)
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Inventory(Base):
    __tablename__ = "inventory"
    __table_args__ = (
        Index("idx_inventory_status", "user_id", "status"),
        Index("idx_inventory_expire", "expire_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    device_id: Mapped[str | None] = mapped_column(String(36))
    item_name: Mapped[str] = mapped_column(String(64))
    normalized_name: Mapped[str | None] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(16), default="其他")
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), default=1)
    unit: Mapped[str] = mapped_column(String(8), default="个")
    location: Mapped[str] = mapped_column(String(16), default="冷藏")
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    expire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expire_days: Mapped[int | None] = mapped_column()
    source: Mapped[str] = mapped_column(String(16), default="voice")
    raw_text: Mapped[str | None] = mapped_column(Text)
    # active | consumed | removed | expired | pending（ADR-9 待确认）
    status: Mapped[str] = mapped_column(String(16), default="active")
    confirmed: Mapped[bool] = mapped_column(Boolean, default=True)  # ADR-9：待确认机制
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class OperationLog(Base):
    __tablename__ = "operation_logs"
    __table_args__ = (Index("idx_logs_time", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    inventory_id: Mapped[str | None] = mapped_column(String(36))
    item_name: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(16))  # add|consume|remove|expire|update
    quantity: Mapped[float | None] = mapped_column(Numeric(10, 2))
    unit: Mapped[str | None] = mapped_column(String(8))
    location: Mapped[str | None] = mapped_column(String(16))
    raw_text: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), default="voice")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class ShoppingList(Base):
    __tablename__ = "shopping_lists"
    __table_args__ = (Index("idx_shopping_user", "user_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    item_name: Mapped[str] = mapped_column(String(64))
    category: Mapped[str | None] = mapped_column(String(16))
    quantity: Mapped[str] = mapped_column(String(16), default="1")  # 允许模糊量词
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|bought|deleted
    source: Mapped[str] = mapped_column(String(16), default="voice")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    bought_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RecordingLog(Base):
    """录音/消息处理记录（展示软件「对话记录」的数据源）。"""

    __tablename__ = "recording_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    channel: Mapped[str] = mapped_column(String(16), default="web")  # web | wechat | device
    source: Mapped[str] = mapped_column(String(16), default="audio")  # audio | text
    audio_path: Mapped[str | None] = mapped_column(String(256))
    transcript: Mapped[str | None] = mapped_column(Text)      # ASR 原文
    final_text: Mapped[str | None] = mapped_column(Text)      # 替换规则后的文本
    reply_text: Mapped[str | None] = mapped_column(Text)
    plan_json: Mapped[str | None] = mapped_column(Text)       # 结构化解析结果
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Hotword(Base):
    """ASR 热词（让识别更容易听对专有名词）。weight: 1~10。"""

    __tablename__ = "hotwords"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(String(36), index=True, default="demo")
    phrase: Mapped[str] = mapped_column(String(64))
    weight: Mapped[int] = mapped_column(default=3)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class ReplacementRule(Base):
    """识别完成后的文本替换规则（左 → 右）。"""

    __tablename__ = "replacement_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(String(36), index=True, default="demo")
    from_text: Mapped[str] = mapped_column(String(128))
    to_text: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
