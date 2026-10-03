"""热词与替换规则服务（展示软件「词库」页的后端）。"""
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import Hotword, ReplacementRule, User

DEMO_USER = "demo"


def ensure_user(db: Session, user_id: str) -> None:
    """用户不存在时自动创建（演示模式没有真实登录）。"""
    if user_id and not db.get(User, user_id):
        db.add(User(id=user_id, nickname="演示用户"))
        db.commit()


def hotword_phrases(db: Session, user_id: str = DEMO_USER) -> list[dict]:
    """供 ASR 调用的热词列表：[{phrase, weight}]。"""
    return [{"phrase": h.phrase, "weight": h.weight} for h in load_hotwords(db, user_id)]


def load_hotwords(db: Session, user_id: str = DEMO_USER) -> list[Hotword]:
    return list(db.scalars(
        select(Hotword).where(Hotword.user_id == user_id).order_by(Hotword.created_at)
    ))


def save_hotwords(db: Session, phrases: list[dict], user_id: str = DEMO_USER) -> None:
    """整体覆盖保存。phrases: [{phrase, weight}]；空 phrase 忽略；去重。"""
    db.execute(delete(Hotword).where(Hotword.user_id == user_id))
    seen: set[str] = set()
    for p in phrases:
        phrase = str(p.get("phrase", "")).strip()
        if not phrase or phrase in seen:
            continue
        seen.add(phrase)
        try:
            weight = int(p.get("weight", 3))
        except (TypeError, ValueError):
            weight = 3
        db.add(Hotword(user_id=user_id, phrase=phrase[:64], weight=max(1, min(10, weight))))
    db.commit()


def load_rules(db: Session, user_id: str = DEMO_USER) -> list[ReplacementRule]:
    return list(db.scalars(
        select(ReplacementRule).where(ReplacementRule.user_id == user_id)
        .order_by(ReplacementRule.created_at)
    ))


def save_rules(db: Session, rules: list[dict], user_id: str = DEMO_USER) -> None:
    """整体覆盖保存。rules: [{from_text, to_text}]。"""
    db.execute(delete(ReplacementRule).where(ReplacementRule.user_id == user_id))
    for r in rules:
        from_text = str(r.get("from_text", "")).strip()
        to_text = str(r.get("to_text", "")).strip()
        if not from_text or not to_text:
            continue
        db.add(ReplacementRule(
            user_id=user_id, from_text=from_text[:128], to_text=to_text[:128],
        ))
    db.commit()


def apply_replacement_rules(db: Session, text: str, user_id: str = DEMO_USER) -> tuple[str, list[dict]]:
    """按创建顺序应用替换规则，返回 (应用后文本, 命中的规则列表)。"""
    applied: list[dict] = []
    for rule in load_rules(db, user_id):
        if rule.from_text and rule.from_text in text:
            text = text.replace(rule.from_text, rule.to_text)
            applied.append({"from": rule.from_text, "to": rule.to_text})
    return text, applied
