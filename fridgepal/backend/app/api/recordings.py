"""录音/消息处理链路：音频或文字 → ASR → 替换规则 → LLM 解析 → 执行 → 回复。

这是展示软件「语音记账」与「对话记录」的后端，也是后续键盘板固件上传的入口。
"""
import json
import logging
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings, APP_ROOT
from ..db import get_db
from ..models import Inventory, RecordingLog
from ..schemas import ChatResponse
from ..services import dashscope_service, hotwords_service, llm_service
from ..services.card_renderer import render_inventory_card
from ..services.inventory_service import apply_actions

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/recordings", tags=["录音链路"])

_uploaded_audio = APP_ROOT / "uploads" / "audio"
_intent_cn = {
    "upsert_inventory": "add",
    "consume_inventory": "consume",
    "remove_inventory": "remove",
}
# 门开场景：用户没说动作的物品默认是「取出」（人站在开着的冰箱前回答拿了什么）
_PUT_VERB_RE = re.compile(r"(放|买|加|存|塞|补|囤|进)")


@router.post("")
def create_recording(
    user_id: str = Form("demo"),
    channel: str = Form("web"),
    text: str | None = Form(None),
    zone: str | None = Form(None),
    audio: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    """上传一段录音（wav）或一段文字，走完整链路，返回识别与执行结果。"""
    hotwords_service.ensure_user(db, user_id)
    transcript: str | None = None
    audio_rel_path: str | None = None

    if audio is not None:
        _uploaded_audio.mkdir(parents=True, exist_ok=True)
        suffix = Path(audio.filename or "audio.wav").suffix or ".wav"
        path = _uploaded_audio / f"rec_{uuid.uuid4().hex[:12]}{suffix}"
        path.write_bytes(audio.file.read())
        audio_rel_path = f"uploads/audio/{path.name}"
        if settings.asr_mode == "dashscope":
            try:
                phrases = hotwords_service.hotword_phrases(db, user_id)
                transcript = dashscope_service.transcribe_wav(path, phrases)
            except Exception as e:
                logger.exception("ASR 失败")
                db.add(RecordingLog(
                    user_id=user_id, channel=channel, source="audio",
                    audio_path=audio_rel_path, ok=False, reply_text=f"语音识别失败：{e}",
                ))
                db.commit()
                raise HTTPException(status_code=502, detail=f"语音识别失败：{e}")
        else:
            transcript = None
    elif text:
        transcript = text.strip()
    else:
        raise HTTPException(status_code=400, detail="需要 audio 或 text 至少一项")

    # 替换规则（识别完成后把左词替换为右词）
    final_text = transcript or ""
    applied_rules: list[dict] = []
    if transcript is not None:
        final_text, applied_rules = hotwords_service.apply_replacement_rules(db, transcript, user_id)

    # 解析 + 执行
    reply, actions, plan_intent = _execute(db, user_id, channel, final_text, zone)
    # 收缩原则：仅查询语音播报；放入/消耗静默
    speak_flag = plan_intent == "query_inventory"

    db.add(RecordingLog(
        user_id=user_id, channel=channel,
        source="audio" if audio else "text",
        audio_path=audio_rel_path,
        transcript=transcript, final_text=final_text,
        reply_text=reply, plan_json=json.dumps(actions, ensure_ascii=False), ok=True,
    ))
    db.commit()
    return {
        "transcript": transcript,
        "final_text": final_text,
        "applied_rules": applied_rules,
        "reply": reply,
        "speak": speak_flag,
        "intent": plan_intent,
        "actions": actions,
        "audio_url": audio_rel_path,
    }


@router.get("")
def list_recordings(limit: int = 50, db: Session = Depends(get_db)):
    """对话记录（新的在前）。"""
    rows = list(db.scalars(
        select(RecordingLog).order_by(RecordingLog.created_at.desc()).limit(limit)
    ))
    return [
        {
            "id": r.id,
            "channel": r.channel,
            "source": r.source,
            "transcript": r.transcript,
            "final_text": r.final_text,
            "reply_text": r.reply_text,
            "ok": r.ok,
            "audio_url": r.audio_path,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/card")
def inventory_card(user_id: str = "demo", db: Session = Depends(get_db)):
    """当前库存 → 表格卡片 PNG（公众号推送与展示软件共用）。"""
    rows = list(db.scalars(
        select(Inventory).where(Inventory.user_id == user_id, Inventory.status == "active")
    ))
    path = render_inventory_card(rows)
    return FileResponse(path, media_type="image/png", filename="fridge-card.png")


@router.get("/tts")
def tts_get(text: str = Query(...)):
    """GET 版本：板子固件和快速测试用（等价 POST /tts）。"""
    return tts(text=text)


@router.post("/tts")
def tts(text: str = Form(...)):
    """文字 → 语音 WAV（基座问句「拿了什么？」的生成入口）。"""
    try:
        path = dashscope_service.synthesize_tts(text)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TTS 失败：{e}")
    return FileResponse(path, media_type="audio/wav", filename="question.wav")


def _execute(db: Session, user_id: str, channel: str, text: str,
             zone: str | None = None) -> tuple[str, list[dict], str]:
    """解析文本并执行库存/清单操作，返回 (回复文本, actions)。与 ai.chat 同语义。
    zone = 门开场景的分区提示（冷藏/冷冻），只覆盖用户没明说位置的物品。"""
    from ..api.ai import _answer_query

    plan = llm_service.parse_text(text)
    intent = plan["intent"]
    # 门开语义：被问「拿了什么」时，报物品名 = 取出（除非明确说了放/买/加）
    reinterpreted = False
    if zone and intent == "upsert_inventory" and not _PUT_VERB_RE.search(text):
        intent = "consume_inventory"
        reinterpreted = True
    if zone and intent in ("upsert_inventory", "consume_inventory", "remove_inventory"):
        for it in plan.get("items", []):
            if not it.get("location"):
                it["location"] = zone

    if intent in _intent_cn:
        actions = apply_actions(db, user_id, None, plan["items"], _intent_cn[intent], text, channel)
        lines = []
        for a in actions:
            q = a["data"]["quantity"]
            loc = a["data"].get("location")
            name = a["data"]["name"] + (f"（{loc}）" if loc else "")
            lines.append(name if q is None else f"{name} {q:g}{a['data']['unit']}")
        verb = {"upsert_inventory": "已记录", "consume_inventory": "已扣减", "remove_inventory": "已清除"}[intent]
        if reinterpreted:
            verb = "已取出"
        if reinterpreted:
            verb = "已取出"
        return f"{verb}：" + "、".join(lines), actions, intent

    if intent == "query_inventory":
        reply, _display = _answer_query(db, user_id, text)
        return reply, [], intent

    if intent == "create_shopping_list":
        from ..models import ShoppingList
        db.add_all([
            ShoppingList(user_id=user_id, item_name=i["name"],
                         quantity=str(i["quantity"]), source=channel)
            for i in plan["items"]
        ])
        db.commit()
        names = "、".join(i["name"] for i in plan["items"])
        return f"已加入购物清单：{names}", [{"type": "create_shopping_list", "data": {"items": plan["items"]}}], intent

    return "我只管冰箱记账哦～放什么、吃掉什么、要买什么，说一句就行。", [], intent
