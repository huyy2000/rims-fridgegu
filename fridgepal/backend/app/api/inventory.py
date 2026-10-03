"""库存 API（对应开发计划 §5.3）。"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Inventory, OperationLog
from ..schemas import InventoryCreate, InventoryOut, InventoryUpdate

router = APIRouter(prefix="/inventory", tags=["库存"])


def _fmt(row: Inventory) -> InventoryOut:
    return InventoryOut(
        id=row.id,
        item_name=row.item_name,
        category=row.category,
        quantity=float(row.quantity),
        unit=row.unit,
        location=row.location,
        expire_at=row.expire_at,
        status=row.status,
        added_at=row.added_at,
    )


@router.get("", response_model=list[InventoryOut])
def list_inventory(
    user_id: str = Query(...),
    category: str | None = None,
    location: str | None = None,
    status: str = "active",
    db: Session = Depends(get_db),
):
    stmt = (
        select(Inventory)
        .where(Inventory.user_id == user_id, Inventory.status == status)
        .order_by(Inventory.category, Inventory.created_at)
    )
    if category:
        stmt = stmt.where(Inventory.category == category)
    if location:
        stmt = stmt.where(Inventory.location == location)
    return [_fmt(r) for r in db.scalars(stmt).all()]


@router.post("", response_model=InventoryOut)
def create_inventory(
    user_id: str = Query(...),
    body: InventoryCreate = ...,
    db: Session = Depends(get_db),
):
    """手动入库（食材清单页用）。同名同单位同位置自动合并；未填保质期按品类默认。"""
    from datetime import timedelta

    from ..services.llm_service import category_of, default_location

    category, default_days = category_of(body.item_name)
    expire_days = body.expire_days if body.expire_days else default_days
    location = body.location or default_location(body.item_name)
    if location == "冷冻":
        expire_days = max(expire_days, 90)  # 冷冻大幅延长保质期
    new_exp = datetime.now(timezone.utc) + timedelta(days=expire_days)

    stmt = (
        select(Inventory)
        .where(
            Inventory.user_id == user_id,
            Inventory.item_name == body.item_name,
            Inventory.unit == body.unit,
            Inventory.location == location,
            Inventory.status == "active",
        )
        .order_by(Inventory.created_at)
    )
    existing = db.scalars(stmt).first()
    if existing is not None:
        existing.quantity = float(existing.quantity) + float(body.quantity)
        old_exp = existing.expire_at
        if old_exp is not None and old_exp.tzinfo is None:
            old_exp = old_exp.replace(tzinfo=timezone.utc)  # SQLite 取回是 naive
        if old_exp is None or new_exp < old_exp:
            existing.expire_at = new_exp
            existing.expire_days = expire_days
        db.add(OperationLog(
            user_id=user_id, inventory_id=existing.id, item_name=body.item_name,
            action="add", quantity=body.quantity, unit=body.unit, source="manual",
        ))
        db.commit()
        db.refresh(existing)
        return _fmt(existing)

    row = Inventory(
        user_id=user_id,
        item_name=body.item_name,
        normalized_name=body.item_name,
        category=category,
        quantity=body.quantity,
        unit=body.unit,
        location=location,
        expire_days=expire_days,
        expire_at=new_exp,
        source="manual",
    )
    db.add(row)
    db.add(OperationLog(
        user_id=user_id, inventory_id=None, item_name=body.item_name,
        action="add", quantity=body.quantity, unit=body.unit,
        location=location, source="manual",
    ))
    db.commit()
    db.refresh(row)
    return _fmt(row)


@router.patch("/{item_id}", response_model=InventoryOut)
def update_inventory(
    item_id: str,
    body: InventoryUpdate,
    user_id: str = Query(...),
    db: Session = Depends(get_db),
):
    row = db.get(Inventory, item_id)
    if not row or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="记录不存在")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.add(OperationLog(
        user_id=user_id, inventory_id=row.id, item_name=row.item_name,
        action="update", source="manual",
    ))
    db.commit()
    db.refresh(row)
    return _fmt(row)


@router.delete("/{item_id}")
def delete_inventory(
    item_id: str,
    user_id: str = Query(...),
    db: Session = Depends(get_db),
):
    row = db.get(Inventory, item_id)
    if not row or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="记录不存在")
    row.status = "removed"
    row.consumed_at = datetime.now(timezone.utc)
    db.add(OperationLog(
        user_id=user_id, inventory_id=row.id, item_name=row.item_name,
        action="remove", source="manual",
    ))
    db.commit()
    return {"ok": True}


@router.post("/consume")
def consume(
    user_id: str = Query(...),
    items: list[dict] = ...,
    db: Session = Depends(get_db),
):
    """批量扣减（供 LLM 网关调用）。"""
    from ..services.inventory_service import apply_actions

    actions = apply_actions(
        db, user_id, None, items, "consume", raw_text="", source="manual"
    )
    return {"ok": True, "actions": actions}


@router.get("/expiring", response_model=list[InventoryOut])
def expiring(
    user_id: str = Query(...),
    days: int = 3,
    db: Session = Depends(get_db),
):
    """查询临期（默认 3 天内到期）。"""
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(days=days)
    stmt = (
        select(Inventory)
        .where(
            Inventory.user_id == user_id,
            Inventory.status == "active",
            Inventory.expire_at.is_not(None),
            Inventory.expire_at <= deadline,
        )
        .order_by(Inventory.expire_at)
    )
    return [_fmt(r) for r in db.scalars(stmt).all()]


@router.get("/summary")
def summary(user_id: str = Query(...), db: Session = Depends(get_db)):
    """按分类统计（H5 首页摘要）。"""
    stmt = (
        select(Inventory.category, func.count(Inventory.id), func.sum(Inventory.quantity))
        .where(Inventory.user_id == user_id, Inventory.status == "active")
        .group_by(Inventory.category)
    )
    return [
        {"category": cat, "count": cnt, "total_quantity": float(qty or 0)}
        for cat, cnt, qty in db.execute(stmt).all()
    ]
