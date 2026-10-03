"""购物清单 API（对应开发计划 §5.4）。"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ShoppingList
from ..schemas import ShoppingItemCreate, ShoppingItemOut

router = APIRouter(prefix="/shopping", tags=["购物清单"])


@router.get("", response_model=list[ShoppingItemOut])
def list_items(
    user_id: str = Query(...),
    status: str = "pending",
    db: Session = Depends(get_db),
):
    stmt = (
        select(ShoppingList)
        .where(ShoppingList.user_id == user_id, ShoppingList.status == status)
        .order_by(ShoppingList.created_at)
    )
    return list(db.scalars(stmt).all())


@router.post("", response_model=ShoppingItemOut)
def create_item(
    user_id: str = Query(...),
    body: ShoppingItemCreate = ...,
    db: Session = Depends(get_db),
):
    row = ShoppingList(user_id=user_id, **body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{item_id}", response_model=ShoppingItemOut)
def update_item(
    item_id: str,
    user_id: str = Query(...),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
):
    row = db.get(ShoppingList, item_id)
    if not row or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="记录不存在")
    if status:
        row.status = status
        if status == "bought":
            row.bought_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{item_id}")
def delete_item(
    item_id: str,
    user_id: str = Query(...),
    db: Session = Depends(get_db),
):
    row = db.get(ShoppingList, item_id)
    if not row or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="记录不存在")
    row.status = "deleted"
    db.commit()
    return {"ok": True}


@router.post("/batch")
def batch_create(
    user_id: str = Query(...),
    items: list[ShoppingItemCreate] = ...,
    db: Session = Depends(get_db),
):
    """批量添加（LLM 网关用）。"""
    rows = [ShoppingList(user_id=user_id, **i.model_dump()) for i in items]
    db.add_all(rows)
    db.commit()
    return {"ok": True, "count": len(rows)}
