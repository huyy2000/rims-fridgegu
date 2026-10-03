"""AI 对话网关（对应开发计划 §5.5）：语音/微信共用同一入口。

流程：文字 → LLM 意图解析 → 执行库存/清单操作 → 生成回复。
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Inventory, ShoppingList
from ..schemas import ChatRequest, ChatResponse
from ..services import inventory_service, llm_service

router = APIRouter(prefix="/ai", tags=["AI 对话"])

_INTENT_CN = {
    "upsert_inventory": "add",
    "consume_inventory": "consume",
    "remove_inventory": "remove",
}


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    plan = llm_service.parse_text(req.text)
    intent = plan["intent"]

    # 1) 库存操作：执行并生成回复
    if intent in _INTENT_CN:
        actions = inventory_service.apply_actions(
            db, req.user_id, None, plan["items"],
            _INTENT_CN[intent], req.text, req.channel,
        )
        lines = []
        for a in actions:
            q = a["data"]["quantity"]
            lines.append(a["data"]["name"] if q is None else f"{a['data']['name']} {q:g}{a['data']['unit']}")
        verb = {"upsert_inventory": "已记录", "consume_inventory": "已扣减", "remove_inventory": "已清除"}[intent]
        reply = f"{verb}：" + "、".join(lines)
        return ChatResponse(reply_text=reply, display_text="  ".join(lines), actions=actions)

    # 2) 库存查询
    if intent == "query_inventory":
        reply, display = _answer_query(db, req.user_id, req.text)
        return ChatResponse(reply_text=reply, display_text=display)

    # 3) 购物清单
    if intent == "create_shopping_list":
        rows = [
            ShoppingList(
                user_id=req.user_id, item_name=i["name"],
                quantity=str(i["quantity"]), source=req.channel,
            )
            for i in plan["items"]
        ]
        db.add_all(rows)
        db.commit()
        names = "、".join(i["name"] for i in plan["items"])
        return ChatResponse(
            reply_text=f"已加入购物清单：{names}",
            actions=[{"type": "create_shopping_list", "data": {"items": plan["items"]}}],
        )

    # 4) 兜底（收缩原则：只做冰箱记账，其余不接）
    return ChatResponse(
        reply_text="我只管冰箱记账哦～放什么、吃掉什么、要买什么，说一句就行。"
    )


def _answer_query(db: Session, user_id: str, text: str) -> tuple[str, str]:
    """简单查询回答（Mock 阶段）。TODO(M1 后)：接 DeepSeek 做智能问答。"""
    now = datetime.now(timezone.utc)
    if "临期" in text or "快过期" in text:
        rows = list(db.scalars(
            select(Inventory).where(
                Inventory.user_id == user_id,
                Inventory.status == "active",
                Inventory.expire_at.is_not(None),
                Inventory.expire_at <= now + timedelta(days=3),
            ).order_by(Inventory.expire_at)
        ))
        if not rows:
            return "3 天内没有临期食材。", "无临期"
        lines = [f"{r.item_name}（{r.expire_at:%m-%d} 到期）" for r in rows[:5]]
        return "临期提醒：" + "、".join(lines), "临期：" + " ".join(lines)

    rows = list(db.scalars(
        select(Inventory).where(
            Inventory.user_id == user_id, Inventory.status == "active"
        ).order_by(Inventory.category, Inventory.created_at)
    ))
    if not rows:
        return "冰箱里暂时没有库存记录。", "空"
    if any(k in text for k in ("多少", "几个", "还有", "剩")):
        # 只回答提到了具体物品的
        for r in rows:
            if r.item_name in text:
                return (
                    f"{r.item_name}还有 {float(r.quantity):g} {r.unit}",
                    f"{r.item_name} x{float(r.quantity):g}",
                )
    cats: dict[str, list[str]] = {}
    for r in rows:
        cats.setdefault(r.category, []).append(f"{r.item_name} {float(r.quantity):g}{r.unit}")
    if "蔬菜" in text or "肉" in text or "水果" in text or "什么" in text:
        # 分类过滤
        kw = {"蔬菜": "vegetable", "肉": "meat", "水果": "fruit"}.get(
            next((k for k in ("蔬菜", "肉", "水果") if k in text), "")
        )
        if kw:
            cats = {c: v for c, v in cats.items() if c == kw}
    parts = ["、".join(v) for v in cats.values()]
    reply = "冰箱里有：" + "；".join(parts[:6]) if parts else "暂时没有这类库存。"
    return reply, "  ".join(f"{k}:{len(v)}项" for k, v in cats.items())
