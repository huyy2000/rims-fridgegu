"""库存业务逻辑：把 LLM 解析出的结构化操作落到数据库。"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Inventory, OperationLog
from .llm_service import category_of, default_location


def _apply_one(
    db: Session,
    user_id: str,
    device_id: str | None,
    item: dict,
    action: str,
    raw_text: str,
    source: str,
) -> Inventory:
    """对单个物品执行 add / consume / remove，返回受影响记录。"""
    name = item["name"]
    qty_raw = item.get("quantity")
    qty = float(qty_raw) if qty_raw is not None else None  # None = 全部（仅 consume/remove 用）
    unit = item.get("unit", "个")
    category, expire_days = category_of(name)
    # 位置：用户明说 > 常识库（品类/物品默认）；处理链路里 location 缺省为 None
    location = item.get("location") or default_location(name)
    # 冷冻大幅延长保质期（常识：冷藏 3 天的肉冷冻可存数月），下限 90 天
    if location == "冷冻":
        expire_days = max(expire_days, 90)

    if action == "add":
        # 同名 + 同单位 + 同位置的 active 记录合并数量（到期取更早的，先吃先坏）
        stmt = (
            select(Inventory)
            .where(
                Inventory.user_id == user_id,
                Inventory.item_name == name,
                Inventory.unit == unit,
                Inventory.location == location,
                Inventory.status == "active",
            )
            .order_by(Inventory.created_at)
        )
        existing = db.scalars(stmt).first()
        if existing is not None:
            existing.quantity = float(existing.quantity) + float(qty or 0)
            new_exp = datetime.now(timezone.utc) + timedelta(days=expire_days)
            old_exp = existing.expire_at
            if old_exp is not None and old_exp.tzinfo is None:
                old_exp = old_exp.replace(tzinfo=timezone.utc)  # SQLite 取回是 naive
            if old_exp is not None and new_exp < old_exp:
                existing.expire_at = new_exp
                existing.expire_days = expire_days
            existing.raw_text = raw_text
            db.add(OperationLog(
                user_id=user_id, inventory_id=existing.id, item_name=name,
                action="add", quantity=qty, unit=unit, raw_text=raw_text, source=source,
            ))
            return existing

        row = Inventory(
            user_id=user_id,
            device_id=device_id,
            item_name=name,
            normalized_name=name,
            category=category,
            quantity=qty,
            unit=unit,
            location=location,
            expire_days=expire_days,
            expire_at=datetime.now(timezone.utc) + timedelta(days=expire_days),
            source=source,
            raw_text=raw_text,
        )
        db.add(row)
        db.flush()
        db.add(OperationLog(
            user_id=user_id, inventory_id=row.id, item_name=name,
            action="add", quantity=qty, unit=unit, raw_text=raw_text, source=source,
        ))
        return row

    # consume / remove：找当前 active 的库存记录
    stmt = (
        select(Inventory)
        .where(
            Inventory.user_id == user_id,
            Inventory.item_name == name,
            Inventory.status == "active",
        )
        .order_by(Inventory.created_at)
    )
    rows = list(db.scalars(stmt).all())
    total = sum(float(r.quantity) for r in rows)

    if action == "remove":
        for r in rows:
            r.status = "removed"
            r.consumed_at = datetime.now(timezone.utc)
        db.add(OperationLog(
            user_id=user_id, item_name=name, action="remove",
            quantity=None, unit=unit, raw_text=raw_text, source=source,
        ))
        return rows[0] if rows else _empty_row(name)

    # consume：逐条扣减（未指定数量 = 全部吃完）
    requested = item.get("quantity")
    remaining = float(requested) if requested is not None else float("inf")
    consumed = 0.0
    for r in rows:
        if remaining <= 0:
            break
        cur = float(r.quantity)
        take = min(cur, remaining)
        if take >= cur - 1e-9:
            r.status = "consumed"
            r.consumed_at = datetime.now(timezone.utc)
        else:
            r.quantity = cur - take
        consumed += take
        remaining -= take
    db.add(OperationLog(
        user_id=user_id, item_name=name, action="consume",
        quantity=consumed if rows else None, unit=unit,
        raw_text=raw_text, source=source,
    ))
    return rows[0] if rows else _empty_row(name)


def _empty_row(name: str) -> Inventory:
    """扣减不存在的物品时返回的占位对象（仅用于日志展示）。"""
    return Inventory(
        user_id="", item_name=name, category="other", quantity=0,
        unit="个", raw_text=f"（未找到 {name} 的库存记录）",
    )


def apply_actions(
    db: Session,
    user_id: str,
    device_id: str | None,
    items: list[dict],
    action: str,
    raw_text: str,
    source: str,
) -> list[dict]:
    """批量应用操作，返回结构化 actions（供前端/固件执行）。"""
    results: list[dict] = []
    for item in items:
        row = _apply_one(db, user_id, device_id, item, action, raw_text, source)
        qty = item.get("quantity")
        results.append({
            "type": f"{action}_inventory",
            "data": {
                "id": getattr(row, "id", None),
                "name": item["name"],
                "quantity": float(qty) if qty is not None else None,
                "unit": item.get("unit", "个"),
                "category": row.category,
                "status": row.status,
                "location": getattr(row, "location", None),
            },
        })
    db.commit()
    return results
