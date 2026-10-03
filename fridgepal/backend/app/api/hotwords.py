"""词库 API：ASR 热词 + 替换规则（对应展示软件「词库」页）。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import hotwords_service

router = APIRouter(prefix="/vocab", tags=["词库"])


class HotwordItem(BaseModel):
    phrase: str
    weight: int = 3


class RuleItem(BaseModel):
    from_text: str
    to_text: str


class VocabSave(BaseModel):
    hotwords: list[HotwordItem] = []
    rules: list[RuleItem] = []


@router.get("")
def get_vocab(user_id: str = "demo", db: Session = Depends(get_db)):
    hotwords = hotwords_service.load_hotwords(db, user_id)
    rules = hotwords_service.load_rules(db, user_id)
    return {
        "hotwords": [{"phrase": h.phrase, "weight": h.weight} for h in hotwords],
        "rules": [{"from_text": r.from_text, "to_text": r.to_text} for r in rules],
    }


@router.put("")
def put_vocab(body: VocabSave, user_id: str = "demo", db: Session = Depends(get_db)):
    """保存更改（整体覆盖，与前端「保存更改」按钮对应）。"""
    hotwords_service.save_hotwords(db, [i.model_dump() for i in body.hotwords], user_id)
    hotwords_service.save_rules(db, [i.model_dump() for i in body.rules], user_id)
    return {"ok": True}
